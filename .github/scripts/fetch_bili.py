#!/usr/bin/env python3
"""在 GitHub runner 上抓 B 站视频（沙箱到不了 bilibili，让 runner 代劳）。

为什么不是一句 yt-dlp：
  · www.bilibili.com 网页对机房 IP 直接 412；
  · api/x/player/playurl 不带 WBI 签名一律返回 {"code":-412,"message":"request was banned"}；
  · 未登录最高 480P（qn=32），带 Cookie 才给 720P+（本脚本没有账号 Cookie，所以按 32 起步）。

策略（谁通用谁，全部写日志）：
  1. finger/spi 取 buvid3/buvid4，再补 b_nut/_uuid/b_lsid，凑出「像浏览器」的 Cookie 罐
  2. nav 取 img_key/sub_key → mixin key → 给 playurl 加 wts + w_rid（WBI 签名）
  3. 先试 fnval=1（单文件 mp4，含音轨），再试 fnval=16/4048（DASH，音视频分轨后 ffmpeg 合并）
  4. 每档清晰度按 80/64/32/16 依次降级

用法：python3 fetch_bili.py BV1suxg6MEJz /tmp/out
退出码 0 = 拿到了文件。
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
REF = "https://www.bilibili.com/"
API = "https://api.bilibili.com"
# CDN 直链的主机部分是「可换的」：path+query 才是签名，
# 567 / 403 多半是当前镜像对机房 IP 不友好，换主机即可。
MIRRORS = [
    "upos-sz-mirrorcos.bilivideo.com",
    "upos-sz-mirrorali.bilivideo.com",
    "upos-sz-mirrorhw.bilivideo.com",
    "upos-sz-mirror08c.bilivideo.com",
    "upos-sz-mirrorcosb.bilivideo.com",
    "upos-sz-mirroraliov.bilivideo.com",
    "upos-hz-mirrorakam.akamaized.net",
]
MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def log(*a):
    print(*a, flush=True)


def http(url, cookie="", referer=REF, timeout=40, binary=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": referer,
        "Origin": "https://www.bilibili.com",
        "Accept": "*/*" if binary else "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        **({"Cookie": cookie} if cookie else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}".encode()


def cookie_jar():
    """凑一份像浏览器的 Cookie：buvid3/buvid4 来自官方 spi，其余按社区文档造。"""
    st, body = http(f"{API}/x/frontend/finger/spi")
    b3 = b4 = ""
    try:
        d = json.loads(body)["data"]
        b3, b4 = d.get("b_3", ""), d.get("b_4", "")
    except Exception:  # noqa: BLE001
        log("spi 解析失败:", st, body[:160])
    uid = f"{int(time.time() * 1000) % 100000}{random.randint(10000, 99999)}"
    uuid = "-".join([
        "".join(random.choice("0123456789ABCDEF") for _ in range(8)),
        "".join(random.choice("0123456789ABCDEF") for _ in range(4)),
        "".join(random.choice("0123456789ABCDEF") for _ in range(4)),
        "".join(random.choice("0123456789ABCDEF") for _ in range(4)),
        "".join(random.choice("0123456789ABCDEF") for _ in range(12)),
    ]) + "infoc"
    jar = {
        "buvid3": b3,
        "buvid4": b4,
        "b_nut": str(int(time.time())),
        "_uuid": uuid,
        "b_lsid": f"{random.randint(0x10000000, 0xFFFFFFFF):08X}_{int(time.time()*1000):X}",
        "CURRENT_FNVAL": "4048",
        "language": "zh-CN",
    }
    jar = {k: v for k, v in jar.items() if v}
    return "; ".join(f"{k}={v}" for k, v in jar.items()), b3


def mixin_key(cookie=""):
    st, body = http(f"{API}/x/web-interface/nav", cookie)
    try:
        wbi = json.loads(body)["data"]["wbi_img"]
        img = wbi["img_url"].rsplit("/", 1)[-1].split(".")[0]
        sub = wbi["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    except Exception as e:  # noqa: BLE001
        log("nav/wbi_img 取不到:", st, body[:200], e)
        return ""
    raw = img + sub
    key = "".join(raw[i] for i in MIXIN_TAB if i < len(raw))[:32]
    log(f"mixin key: {key[:8]}…（{len(key)} 位）")
    return key


def sign(params: dict, key: str) -> str:
    p = dict(params)
    p["wts"] = int(time.time())
    q = urllib.parse.urlencode(
        {k: re.sub(r"[!'()*]", "", str(v)) for k, v in sorted(p.items())},
        quote_via=urllib.parse.quote, safe="")
    return q + "&w_rid=" + hashlib.md5((q + key).encode()).hexdigest()


def main() -> int:
    bvid = sys.argv[1] if len(sys.argv) > 1 else "BV1suxg6MEJz"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/out"
    os.makedirs(outdir, exist_ok=True)
    cookie, _ = cookie_jar()
    log("cookie:", cookie[:80], "…")

    st, body = http(f"{API}/x/web-interface/view?bvid={bvid}", cookie)
    log("view:", st)
    if st != 200 or json.loads(body).get("code") != 0:
        log("view 失败:", body[:200])
        return 1
    v = json.loads(body)["data"]
    aid, cid, title, dur = v["aid"], v["cid"], v["title"], v["duration"]
    log(f"title={title} aid={aid} cid={cid} dur={dur}s")
    json.dump({"bvid": bvid, "aid": aid, "cid": cid, "title": title,
               "duration": dur, "pages": [{"cid": p["cid"], "part": p["part"]}
                                          for p in v.get("pages", [])]},
              open(os.path.join(outdir, "meta.json"), "w"), ensure_ascii=False, indent=1)

    key = mixin_key(cookie)
    if not key:
        return 1

    base = {"bvid": bvid, "cid": cid, "fnver": 0, "fourk": 0, "platform": "pc"}
    attempts = [
        ("durl qn=80", {**base, "qn": 80, "fnval": 1}, "durl"),
        ("durl qn=64", {**base, "qn": 64, "fnval": 1}, "durl"),
        ("durl qn=32", {**base, "qn": 32, "fnval": 1}, "durl"),
        ("dash qn=80", {**base, "qn": 80, "fnval": 4048}, "dash"),
        ("dash qn=64", {**base, "qn": 64, "fnval": 16}, "dash"),
        ("dash qn=32", {**base, "qn": 32, "fnval": 16}, "dash"),
    ]
    got = None
    for name, params, kind in attempts:
        qs = sign(params, key)
        st, body = http(f"{API}/x/player/wbi/playurl?{qs}", cookie)
        try:
            j = json.loads(body)
        except Exception:  # noqa: BLE001
            log(f"[{name}] 非 JSON: {st} {body[:120]}")
            continue
        log(f"[{name}] http={st} code={j.get('code')} {j.get('message')}")
        if j.get("code") != 0:
            continue
        d = j["data"]
        if kind == "durl" and d.get("durl"):
            got = ("durl", d["durl"], d.get("quality"), d.get("accept_quality"))
        elif kind == "dash" and d.get("dash"):
            got = ("dash", d["dash"], d.get("quality"), d.get("accept_quality"))
        if got:
            log(f"   命中 {name} quality={got[2]} 可选={got[3]}")
            break

    if not got:
        log("所有 playurl 组合都被拒（机房 IP 风控）")
        return 1

    def variants(url, backups):
        out = [url] + list(backups or [])
        for m in MIRRORS:
            out.append(re.sub(r"^https://[^/]+", "https://" + m, url))
        seen, uniq = set(), []
        for u in out:
            if u and u not in seen:
                seen.add(u)
                uniq.append(u)
        return uniq

    def fetch(url, path, backups=None, cookie=""):
        """逐变体试探：镜像 × 请求头组合 × curl/http1.1，日志写状态码。"""
        hdrs = [
            ["-e", REF],
            ["-e", REF, "-H", f"Cookie: {cookie}"],
            ["-e", REF, "-H", "Origin: https://www.bilibili.com",
             "-H", "Range: bytes=0-"],
        ]
        for u in variants(url, backups):
            for hi, h in enumerate(hdrs):
                cmd = ["curl", "-sS", "--http1.1", "-L", "--max-time", "300",
                       "-A", UA, "-o", path, "-w", "%{http_code} %{size_download}"] + h + [u]
                r = subprocess.run(cmd, capture_output=True, text=True)
                code = (r.stdout or "").split()
                c = code[0] if code else "?"
                size = int(code[1]) if len(code) > 1 and code[1].isdigit() else 0
                host = re.sub(r"^https://([^/]+).*", r"\1", u)
                log(f"   {host} headers#{hi} -> {c} {size} B")
                if c in ("200", "206") and size > 102400:
                    return size
        return 0

    if got[0] == "durl":
        segs = got[1]
        log(f"durl 段数={len(segs)}")
        parts = []
        for i, seg in enumerate(segs):
            out = os.path.join(outdir, f"source-seg{i}.mp4")
            n = fetch(seg["url"], out, seg.get("backup_url"), cookie)
            log(f"   seg{i} bytes={n}")
            if not n:
                return 1
            parts.append(out)
        out = os.path.join(outdir, "source.mp4")
        if len(parts) == 1:
            os.replace(parts[0], out)
        else:
            with open(out, "wb") as w:
                for f_ in parts:
                    w.write(open(f_, "rb").read())
        log("source.mp4:", os.path.getsize(out))
        return 0

    dash = got[1]
    vs = sorted(dash["video"], key=lambda x: (x.get("id", 0), x.get("bandwidth", 0)))
    aud = sorted(dash.get("audio") or [], key=lambda x: x.get("bandwidth", 0))
    vurl = vs[-1].get("baseUrl") or vs[-1].get("base_url")
    log(f"dash video id={vs[-1].get('id')} {vs[-1].get('width')}x{vs[-1].get('height')}")
    vp = os.path.join(outdir, "v.m4s")
    log("bytes(v):", fetch(vurl, vp, vs[-1].get("backupUrl") or vs[-1].get("backup_url"), cookie))
    if not aud:
        os.rename(vp, os.path.join(outdir, "source.mp4"))
        return 0
    aurl = aud[-1].get("baseUrl") or aud[-1].get("base_url")
    ap = os.path.join(outdir, "a.m4s")
    log("bytes(a):", fetch(aurl, ap, aud[-1].get("backupUrl") or aud[-1].get("backup_url"), cookie))
    out = os.path.join(outdir, "source.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", vp, "-i", ap,
                    "-c", "copy", out], check=True)
    log("merged:", os.path.getsize(out), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
