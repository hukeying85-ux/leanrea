#!/usr/bin/env python3
"""
relay_worker.py — runs INSIDE the GitHub Actions runner (unrestricted egress).

For every URL in .mediaqueue/urls.txt it tries, in order:
  1. yt-dlp          (video-first: YouTube / B站 / 抖音 / 快手 / TikTok / IG)
  2. gallery-dl      (album-first: Instagram / Pinterest / 微博 / TikTok)
  3. xhs-dump        (小红书: yt-dlp --dump-single-json 取原图列表)
  4. html-scrape     (last resort: pull every CDN image URL out of the page)

Results land in media-raw/<云盘目录名>/<slug>/ with a meta.json; a summary is
written to media-raw/_LAST_RUN.md

Exit code is always 0 — one platform failing must not cancel the others.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "media-raw")
QUEUE = os.path.join(ROOT, ".mediaqueue", "urls.txt")

PLATFORM_OF = [
    ("01_小红书素材", ["xiaohongshu.com", "xhscdn.com"]),
    ("02_抖音素材", ["douyin.com", "iesdouyin.com"]),
    ("03_YouTube素材", ["youtube.com", "youtu.be"]),
    ("05_B站素材", ["bilibili.com"]),
    ("06_快手素材", ["kuaishou.com", "chenzhongtech.com"]),
    ("07_TikTok素材", ["tiktok.com"]),
    ("08_Instagram素材", ["instagram.com", "cdninstagram.com"]),
    ("04_其他平台素材", []),
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

IMG_CDN = re.compile(
    r"https?://[^\s\"'\\<>]+?\.(?:jpg|jpeg|png|webp)(?:\?[^\s\"'\\<>]*)?", re.I)


def platform_of(url):
    low = url.lower()
    for folder, keys in PLATFORM_OF:
        if any(k in low for k in keys):
            return folder
    return "04_其他平台素材"


def slug_of(url):
    m = re.search(r"/(?:video|explore|p|reel|status|note)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else hashlib.sha1(url.encode()).hexdigest()[:12]


def run(cmd, timeout=300):
    """返回 (rc, stdout, stderr)。"""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as e:
        return 99, "", f"{type(e).__name__}: {e}"


MEDIA_EXT = {".mp4", ".m4v", ".webm", ".mov", ".mkv", ".flv", ".avi",
             ".m4a", ".mp3", ".aac", ".opus", ".flac"}


def is_media(name):
    return os.path.splitext(name)[1].lower() in MEDIA_EXT


# cookie 注入：内容走 GitHub Actions Secrets，按域名挂给 yt-dlp / gallery-dl
COOKIE_ENV = {
    "douyin.com": "COOKIES_DOUYIN",
    "youtube.com": "COOKIES_YOUTUBE",
    "youtu.be": "COOKIES_YOUTUBE",
    "bilibili.com": "COOKIES_BILIBILI",
    "xiaohongshu.com": "COOKIES_XHS",
    "instagram.com": "COOKIES_INSTAGRAM",
    "weibo.com": "COOKIES_WEIBO",
    "kuaishou.com": "COOKIES_KUAISHOU",
}


def write_cookies_file(domain, pairs, out):
    """pairs: dict|list[tuple] -> Netscape 格式。"""
    if not pairs:
        return None
    items = pairs.items() if isinstance(pairs, dict) else pairs
    path = os.path.join(out, "_cookies.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for k, v in items:
            f.write(f".{domain.lstrip('.')}\tTRUE\t/\tFALSE\t0\t{k}\t{v}\n")
    return path


def cookies_for(url, out):
    """按 URL 域名取 cookie 文件（Secrets 优先，其次官方指纹自举）。"""
    low = url.lower()
    for dom, envname in COOKIE_ENV.items():
        if dom in low:
            raw = os.environ.get(envname, "").strip()
            if raw:
                pairs = []
                for part in raw.replace("\n", ";").split(";"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        pairs.append((k.strip(), v.strip()))
                p = write_cookies_file(dom, pairs, out)
                if p:
                    return p
    if "bilibili.com" in low:
        # B站对机房 IP 返回 412；带上官方接口发的 buvid3/buvid4 指纹可解
        try:
            r = requests.get("https://api.bilibili.com/x/frontend/finger/spi",
                             headers={"User-Agent": UA,
                                      "Referer": "https://www.bilibili.com/"}, timeout=30)
            d = r.json().get("data") or {}
            if d.get("b_3"):
                return write_cookies_file("bilibili.com",
                                          [("buvid3", d["b_3"]),
                                           ("buvid4", d.get("b_4", "")),
                                           ("b_nut", "100")], out)
        except Exception:
            pass
    return None


def list_files_recursive(root):
    out = []
    for d, _, fs in os.walk(root):
        for f in fs:
            if f.endswith((".part", ".ytdl", ".json")) and f != "meta.json":
                continue
            out.append(os.path.relpath(os.path.join(d, f), root))
    return sorted(set(out))


# --------------------------------------------------------------------------
# 0. cookie 自举：抖音/微博这类只要「新鲜匿名 cookie」，不一定要登录态
# --------------------------------------------------------------------------
def bootstrap_cookies(url, out):
    try:
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        host = re.match(r"https?://([^/]+)", url).group(1)
        r = s.get(url, timeout=30)
        cookies = s.cookies.get_dict()
        # 从 Set-Cookie 里再捞一遍（session 有时不收 http-only 之外的）
        for m in re.finditer(r"([^=;\s]+)=([^;]*);", "\n".join(r.headers.get_all("set-cookie", []))):
            cookies.setdefault(m.group(1), m.group(2))
        if not cookies:
            return None
        path = os.path.join(out, "_cookies.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for k, v in cookies.items():
                f.write(f"{host}\tTRUE\t/\tFALSE\t0\t{k}\t{v}\n")
        return path
    except Exception:
        return None


# --------------------------------------------------------------------------
# 1. yt-dlp
# --------------------------------------------------------------------------
YT_BASE = ["yt-dlp", "--no-warnings", "--no-playlist", "--ignore-errors",
           "--no-color", "--user-agent", UA, "--referer", "https://www.google.com/",
           "--write-info-json", "--write-thumbnail", "--convert-thumbnails", "jpg",
           "--retries", "5", "--socket-timeout", "30"]

FORMATS = [
    "bv*[height<=480]+ba/b[height<=480]",   # 首选：480p 音视频分离后合并
    "18/22/43/b",                            # YouTube 传统渐进式单文件（最抗风控）
    "b",                                     # 退一步：最好的单文件
    "bv*+ba/b",                              # 再退：不管分辨率
    "worst",                                 # 保底
]


def try_ytdlp(url, out):
    logs = []
    cookie_file = cookies_for(url, out)
    if not cookie_file and any(k in url for k in ("douyin.com", "weibo.com")):
        cookie_file = bootstrap_cookies(url, out)
    logs.append(f"cookies: {cookie_file or 'none'}")

    for i, fmt in enumerate(FORMATS):
        cmd = list(YT_BASE) + ["-f", fmt, "--merge-output-format", "mp4",
                               "-o", os.path.join(out, "%(title).50s_%(id)s.%(ext)s"), url]
        if cookie_file:
            cmd += ["--cookies", cookie_file]
        if "youtube.com" in url or "youtu.be" in url:
            # 轮换 player client，绕过「Requested format is not available」
            clients = ["web_safari,mweb", "android_vr,ios", "tv,web_embedded"]
            cmd += ["--extractor-args", f"youtube:player_client={clients[i % len(clients)]}"]
        rc, so, se = run(cmd, timeout=1200)
        logs.append(f"-f {fmt} -> rc={rc} {se.strip()[-200:]}")
        files = [f for f in list_files_recursive(out)
                 if not f.startswith("_") and f != "meta.json"]
        # 缩略图不算成功：--write-thumbnail 总会写，会把失败伪装成成功
        if [f for f in files if is_media(f)]:
            return True, "\n".join(logs), files
    return False, "\n".join(logs), []


# --------------------------------------------------------------------------
# 2. gallery-dl
# --------------------------------------------------------------------------
def try_gallerydl(url, out):
    rc, so, se = run(["gallery-dl", "--no-colors", "--dest", out, url], timeout=1200)
    files = [f for f in list_files_recursive(out) if not f.startswith("_") and f != "meta.json"]
    return (rc == 0 and bool(files)), f"rc={rc} {se.strip()[-300:]}", files


# --------------------------------------------------------------------------
# 3. 小红书专用：yt-dlp 能解析页面，只是图片笔记没有 video format
# --------------------------------------------------------------------------
def try_xhs_dump(url, out):
    urls = []

    # A. yt-dlp dump（视频笔记能 dump 出来；图片笔记它会直接报错）
    rc, so, se = run(["yt-dlp", "--no-warnings", "--no-playlist", "--user-agent", UA,
                      "--dump-single-json", url], timeout=180)
    if rc == 0 and so.strip():
        try:
            data = json.loads(so)
            for t in data.get("thumbnails") or []:
                u = t.get("url") if isinstance(t, dict) else t
                if u:
                    urls.append(u)
            if not urls and data.get("thumbnail"):
                urls.append(data["thumbnail"])
        except Exception:
            pass

    # B. 直接解页面里的 __INITIAL_STATE__，拿 imageList（图片笔记走这条）
    if not urls:
        try:
            r = requests.get(url, headers={"User-Agent": UA,
                                           "Accept-Language": "zh-CN,zh;q=0.9"}, timeout=45)
            html = r.text.replace("\\u002F", "/").replace("\\/", "/")
            for key in ("urlDefault", "urlPre", "url"):
                urls += re.findall(rf'"{key}"\s*:\s*"(https?:[^"]+?)"', html)
            urls = [u for u in urls if "xhscdn" in u or "xiaohongshu" in u] or urls
        except Exception as e:
            if not urls:
                return False, f"dump rc={rc} {se.strip()[-160:]} | page: {type(e).__name__}", []

    if not urls:
        return False, f"dump rc={rc} {se.strip()[-160:]} | no image urls in page", []

    cleaned, seen = [], set()
    for u in urls:
        # 去掉小红书的降质后缀，拿原始大图
        u = re.sub(r"!nd_dft_\w+", "", u)
        u = re.sub(r"\?imageView2/.*$", "", u).replace("\\/", "/")
        if u not in seen:
            seen.add(u)
            cleaned.append(u)

    got = []
    for i, u in enumerate(cleaned[:30]):
        try:
            r = requests.get(u, headers={"User-Agent": UA, "Referer": "https://www.xiaohongshu.com/"},
                             timeout=60)
            if r.status_code == 200 and len(r.content) > 10000:
                ext = ".jpg" if "jpeg" in u.lower() or "jpg" in u.lower() else (
                    ".png" if "png" in u.lower() else ".webp")
                p = os.path.join(out, f"xhs_{i+1:02d}{ext}")
                open(p, "wb").write(r.content)
                got.append(os.path.basename(p))
        except Exception:
            continue
        time.sleep(0.3)
    return bool(got), f"dumped {len(cleaned)} urls, saved {len(got)}", got


# --------------------------------------------------------------------------
# 3.5 B站专用：网页端 412（WAF），改走官方 web-interface / playurl 接口
# --------------------------------------------------------------------------
def try_bilibili_api(url, out):
    bv = re.search(r"(BV[0-9A-Za-z]+)", url)
    if not bv:
        return False, "no bvid", []
    bvid = bv.group(1)
    h = {"User-Agent": UA, "Referer": "https://www.bilibili.com/",
         "Origin": "https://www.bilibili.com"}
    try:
        r = requests.get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
                         headers=h, timeout=30)
        try:
            v = r.json()
        except Exception:
            return False, (f"view api non-json: HTTP {r.status_code}, "
                           f"{r.text[:180]!r}"), []
        if v.get("code") != 0:
            return False, f"view api code={v.get('code')} {v.get('message')}", []
        cid = v["data"]["cid"]
        title = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", v["data"]["title"])[:40]
    except Exception as e:
        return False, f"view api: {type(e).__name__}: {e}", []

    logs = [f"bvid={bvid} cid={cid}"]
    for qn, plat in ((32, "html5"), (16, "html5"), (64, "pc")):
        try:
            p = requests.get(
                "https://api.bilibili.com/x/player/playurl",
                params={"bvid": bvid, "cid": cid, "qn": qn, "otype": "json",
                        "fnver": 0, "fnval": 16, "fourk": 1, "platform": plat},
                headers=h, timeout=30).json()
            if p.get("code") != 0:
                logs.append(f"qn{qn}/{plat}: code={p.get('code')}")
                continue
            d = p["data"]
            srcs = []
            if d.get("dash"):
                srcs.append(("v.m4s", [x["baseUrl"] for x in d["dash"]["video"]]))
                srcs.append(("a.m4s", [x["baseUrl"] for x in d["dash"].get("audio", [])]))
            elif d.get("durl"):
                srcs.append(("v.flv", [d["durl"][0]["url"]]))
            if not srcs:
                logs.append(f"qn{qn}/{plat}: no stream")
                continue

            saved = []
            for fname, urls in srcs:
                if not urls:
                    continue
                r = requests.get(urls[0], headers={**h, "Range": "bytes=0-"}, timeout=180, stream=True)
                if r.status_code in (200, 206):
                    pth = os.path.join(out, fname)
                    with open(pth, "wb") as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
                    saved.append(pth)

            final = os.path.join(out, f"{title}_{bvid}.mp4")
            if len(saved) == 2:
                run(["ffmpeg", "-y", "-loglevel", "error", "-i", saved[0], "-i", saved[1],
                     "-c", "copy", final], timeout=600)
            elif saved:
                run(["ffmpeg", "-y", "-loglevel", "error", "-i", saved[0], "-c", "copy", final],
                    timeout=600)
            if os.path.exists(final) and os.path.getsize(final) > 50000:
                for s in saved:
                    try:
                        os.remove(s)
                    except OSError:
                        pass
                return True, "; ".join(logs), [os.path.basename(final)]
            logs.append(f"qn{qn}/{plat}: mux produced nothing")
        except Exception as e:
            logs.append(f"qn{qn}/{plat}: {type(e).__name__}: {e}")
    return False, "; ".join(logs), []


# --------------------------------------------------------------------------
# 3.6 抖音专用：yt-dlp 要 cookie，这里走公开的 iteminfo 接口拿无水印地址
# --------------------------------------------------------------------------
def try_douyin_api(url, out):
    vid = re.search(r"/video/(\d+)", url) or re.search(r"(\d{15,})", url)
    if not vid:
        return False, "no video id", []
    vid = vid.group(1)
    h = {"User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"),
         "Referer": "https://www.douyin.com/"}
    apis = [
        f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={vid}",
        f"https://www.iesdouyin.com/share/video/{vid}/?region=CN&mid=0",
    ]
    data, diag = None, []
    for a in apis:
        try:
            r = requests.get(a, headers=h, timeout=30)
            try:
                j = r.json()
            except Exception:
                diag.append(f"{a.split('/')[2]}: HTTP {r.status_code} non-json {r.text[:100]!r}")
                continue
            if j.get("item_list"):
                data = j
                break
            diag.append(f"{a.split('/')[2]}: keys={list(j)[:5]} status_code={j.get('status_code')}")
        except Exception as e:
            diag.append(f"{a.split('/')[2]}: {type(e).__name__}: {e}")
    if not data:
        return False, " | ".join(diag) or "no item_list", []

    item = data["item_list"][0]
    got = []
    # 图文
    for i, im in enumerate(item.get("images") or []):
        for u in im.get("url_list", [])[:1]:
            try:
                rr = requests.get(u, headers=h, timeout=60)
                if rr.status_code == 200 and len(rr.content) > 10000:
                    p = os.path.join(out, f"douyin_{i+1:02d}.jpg")
                    open(p, "wb").write(rr.content)
                    got.append(os.path.basename(p))
            except Exception:
                continue
    # 视频：playwm -> play 去掉水印
    if not got:
        for u in item.get("video", {}).get("play_addr", {}).get("url_list", []):
            u = u.replace("/playwm/", "/play/").replace("/play/", "/play/")
            try:
                rr = requests.get(u, headers={**h, "Range": "bytes=0-"}, timeout=180, stream=True)
                if rr.status_code in (200, 206):
                    p = os.path.join(out, f"douyin_{vid}.mp4")
                    with open(p, "wb") as f:
                        for c in rr.iter_content(1 << 20):
                            f.write(c)
                    if os.path.getsize(p) > 50000:
                        got.append(os.path.basename(p))
                        break
            except Exception:
                continue
    return bool(got), f"iteminfo ok (images={len(item.get('images') or [])})", got


# --------------------------------------------------------------------------
# 4. 兜底：直接扒页面里的 CDN 图片
# --------------------------------------------------------------------------
def try_scrape(url, out):
    try:
        r = requests.get(url, headers={"User-Agent": UA,
                                       "Accept-Language": "zh-CN,zh;q=0.9"}, timeout=45)
        html = r.text
    except Exception as e:
        return False, f"fetch failed: {type(e).__name__}: {e}", []

    html = html.replace("\\u002F", "/").replace("\\/", "/")
    cands = []
    for pat in (r"https?:[^\s\"'\\<>]*?xhscdn\.com[^\s\"'\\<>]*?\.(?:jpg|jpeg|png|webp)[^\s\"'\\<>]*",
                r"https?:[^\s\"'\\<>]*?sinaimg\.cn[^\s\"'\\<>]*?\.(?:jpg|jpeg|png|webp)[^\s\"'\\<>]*",
                IMG_CDN.pattern):
        cands += re.findall(pat, html, re.I)

    seen, urls = set(), []
    for u in cands:
        u = u.replace("&amp;", "&")
        if u.split("?")[0] not in seen:
            seen.add(u.split("?")[0])
            urls.append(u)

    got = []
    for i, u in enumerate(urls[:30]):
        try:
            rr = requests.get(u, headers={"User-Agent": UA, "Referer": url}, timeout=45)
            if rr.status_code == 200 and len(rr.content) > 8000:
                ext = ".jpg" if "jp" in u.lower()[-12:] else (".png" if "png" in u.lower()[-12:] else ".webp")
                p = os.path.join(out, f"img_{i+1:02d}{ext}")
                open(p, "wb").write(rr.content)
                got.append(os.path.basename(p))
        except Exception:
            continue
        time.sleep(0.3)
    return bool(got), f"found {len(urls)} candidate urls, saved {len(got)}", got


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def handle(url):
    url = url.strip()
    if not url or url.startswith("#"):
        return None
    folder = platform_of(url)
    out = os.path.join(RAW, folder, slug_of(url))
    os.makedirs(out, exist_ok=True)

    chain = [("yt-dlp", try_ytdlp), ("gallery-dl", try_gallerydl), ("scrape", try_scrape)]
    if folder == "01_小红书素材":
        # 图片笔记没有 video format，先走 dump-json 拿原图列表
        chain.insert(0, ("xhs-dump", try_xhs_dump))
    if folder == "05_B站素材":
        chain.insert(1, ("bilibili-api", try_bilibili_api))
    if folder == "02_抖音素材":
        chain.insert(1, ("douyin-api", try_douyin_api))

    steps, ok = [], False
    for name, fn in chain:
        try:
            good, log, _ = fn(url, out)
        except Exception as e:
            good, log = False, f"{type(e).__name__}: {e}"
        steps.append({"tool": name, "ok": bool(good), "log": log})
        if good:
            ok = True
            break

    real = []
    for rel in list_files_recursive(out):
        if rel == "meta.json":
            continue
        p = os.path.join(out, rel)
        if os.path.isfile(p):
            real.append({"name": rel, "bytes": os.path.getsize(p), "sha256": sha256(p)})

    if not real:
        ok = False

    json.dump({
        "source_url": url, "platform_folder": folder,
        "status": "ok" if ok else "failed",
        "tool_used": next((s["tool"] for s in steps if s["ok"]), None),
        "steps": steps, "files": real,
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "素材仅供研究/参考/二次创作底稿，勿直接搬运发布",
    }, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"),
        ensure_ascii=False, indent=2)
    return json.load(open(os.path.join(out, "meta.json"), encoding="utf-8"))


def main():
    if not os.path.exists(QUEUE):
        print("no queue file")
        return
    urls = [l for l in open(QUEUE, encoding="utf-8").read().splitlines() if l.strip()]
    os.makedirs(RAW, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        for m in ex.map(handle, urls):
            if m:
                results.append(m)
                print(f"[{'OK  ' if m['status'] == 'ok' else 'FAIL'}] "
                      f"{m['platform_folder']:<16} {m['source_url'][:60]} "
                      f"-> {len(m['files'])} files "
                      f"({sum(f['bytes'] for f in m['files'])/1048576:.2f} MB)")

    lines = ["# 最近一次中继下载", "",
             f"时间：{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}  ",
             f"任务：{len(results)} 条，成功：{sum(1 for m in results if m['status'] == 'ok')} 条", "",
             "| 平台 | 结果 | 命中工具 | 文件数 | 体积 | 链接 |",
             "|---|---|---|---|---|---|"]
    for m in results:
        size = sum(f["bytes"] for f in m["files"])
        lines.append(f"| {m['platform_folder']} | {'✅' if m['status'] == 'ok' else '❌'} | "
                     f"{m['tool_used'] or '-'} | {len(m['files'])} | {size/1048576:.2f} MB | "
                     f"{m['source_url'][:55]} |")
    lines += ["", "## 逐条明细", ""]
    for m in results:
        lines += [f"### {m['source_url']}", "",
                  f"- 平台目录：`{m['platform_folder']}`",
                  f"- 状态：{m['status']}，命中工具：{m['tool_used'] or '无'}"]
        for f in m["files"]:
            lines.append(f"- `{f['name']}` — {f['bytes']:,} 字节")
        for s in m["steps"]:
            if not s["ok"]:
                lines.append(f"- ❌ {s['tool']}：`{s['log'][:300]}`")
        lines.append("")
    open(os.path.join(RAW, "_LAST_RUN.md"), "w", encoding="utf-8").write("\n".join(lines))
    json.dump(results, open(os.path.join(RAW, "_last_run.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n".join(lines[:16]))


if __name__ == "__main__":
    sys.exit(main())
