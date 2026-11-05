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
    "b",                                     # 退一步：最好的单文件
    "bv*+ba/b",                              # 再退：不管分辨率
    "worst",                                 # 保底
]


def try_ytdlp(url, out):
    logs, cookie_file = [], None
    if "douyin.com" in url or "weibo.com" in url:
        cookie_file = bootstrap_cookies(url, out)

    for i, fmt in enumerate(FORMATS):
        cmd = list(YT_BASE) + ["-f", fmt, "--merge-output-format", "mp4",
                               "-o", os.path.join(out, "%(title).50s_%(id)s.%(ext)s")]
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
        if files:
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
    rc, so, se = run(["yt-dlp", "--no-warnings", "--no-playlist", "--user-agent", UA,
                      "--dump-single-json", url], timeout=180)
    if rc != 0 or not so.strip():
        return False, f"dump failed rc={rc} {se.strip()[-200:]}", []
    try:
        data = json.loads(so)
    except Exception as e:
        return False, f"json parse failed: {e}", []

    urls = []
    for t in data.get("thumbnails") or []:
        u = t.get("url") if isinstance(t, dict) else t
        if u:
            urls.append(u)
    if not urls and data.get("thumbnail"):
        urls.append(data["thumbnail"])

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
        chain.insert(1, ("xhs-dump", try_xhs_dump))

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
