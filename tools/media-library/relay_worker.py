#!/usr/bin/env python3
"""
relay_worker.py — runs INSIDE the GitHub Actions runner (unrestricted egress).

For every URL in .mediaqueue/urls.txt it tries, in order:
  1. yt-dlp          (video-first: YouTube / B站 / 抖音 / 快手 / TikTok / IG / 微博)
  2. gallery-dl      (album-first: Instagram / Pinterest / 微博 / 小红书)
  3. html-scrape     (last resort: pull every CDN image URL out of the page)

Results land in media-raw/<platform-folder>/<slug>/ with a meta.json, and a
summary is written to media-raw/_LAST_RUN.md

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

# 云盘目录名约定 → 域名关键字
PLATFORM_OF = [
    ("01_小红书素材", ["xiaohongshu.com", "xhscdn.com"]),
    ("02_抖音素材", ["douyin.com", "iesdouyin.com"]),
    ("03_YouTube素材", ["youtube.com", "youtu.be"]),
    ("05_B站素材", ["bilibili.com"]),
    ("06_快手素材", ["kuaishou.com", "chenzhongtech.com"]),
    ("07_TikTok素材", ["tiktok.com"]),
    ("08_Instagram素材", ["instagram.com", "cdninstagram.com"]),
    ("04_其他平台素材", []),  # 兜底
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


def slug_of(url, title=""):
    m = re.search(r"/(?:video|explore|p|reel|status|note)/([A-Za-z0-9_-]+)", url)
    token = m.group(1) if m else hashlib.sha1(url.encode()).hexdigest()[:12]
    if title:
        safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", title)[:40].strip("_")
        return f"{safe}_{token}" if safe else token
    return token


def run(cmd, timeout=300):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 99, f"{type(e).__name__}: {e}"


def try_ytdlp(url, out):
    # 480p 封顶，避免把仓库撑爆；拿不到就退到最佳单文件
    fmt = "bv*[height<=480]+ba/b[height<=480]/worst"
    rc, log = run([
        "yt-dlp", "--no-warnings", "--no-playlist", "--ignore-errors",
        "-f", fmt, "--merge-output-format", "mp4",
        "--write-info-json", "--write-thumbnail", "--convert-thumbnails", "jpg",
        "-o", os.path.join(out, "%(title).60s_%(id)s.%(ext)s"), url,
    ], timeout=900)
    files = [f for f in os.listdir(out) if not f.endswith((".part", ".ytdl"))] if os.path.isdir(out) else []
    return rc == 0 and files, log[-1500:], files


def try_gallerydl(url, out):
    rc, log = run(["gallery-dl", "--dest", out, url], timeout=900)
    files = []
    for d, _, fs in os.walk(out):
        files += [os.path.relpath(os.path.join(d, f), out) for f in fs]
    return rc == 0 and files, log[-1500:], files


def try_scrape(url, out):
    """兜底：直接扒页面里的 CDN 图片链接。小红书/微博这类靠这招。"""
    try:
        r = requests.get(url, headers={"User-Agent": UA,
                                       "Accept-Language": "zh-CN,zh;q=0.9"},
                         timeout=45)
        html = r.text
    except Exception as e:
        return False, f"fetch failed: {type(e).__name__}: {e}", []

    # 小红书 / 通用：先解转义，再找图
    html = html.replace("\\u002F", "/").replace("\\/", "/")
    cands = []
    for pat in (r"https?:[^\s\"'\\<>]*?xhscdn\.com[^\s\"'\\<>]*?\.(?:jpg|jpeg|png|webp)[^\s\"'\\<>]*",
                r"https?:[^\s\"'\\<>]*?sinaimg\.cn[^\s\"'\\<>]*?\.(?:jpg|jpeg|png|webp)[^\s\"'\\<>]*",
                IMG_CDN.pattern):
        cands += re.findall(pat, html, re.I)

    seen, urls = set(), []
    for u in cands:
        u = u.replace("&amp;", "&")
        key = u.split("?")[0]
        if key not in seen:
            seen.add(key)
            urls.append(u)
    urls = urls[:30]

    got = []
    for i, u in enumerate(urls):
        try:
            rr = requests.get(u, headers={"User-Agent": UA, "Referer": url}, timeout=45)
            if rr.status_code == 200 and len(rr.content) > 8000:
                ext = ".jpg" if "jpg" in u.lower() or "jpeg" in u.lower() else (
                    ".png" if "png" in u.lower() else ".webp")
                p = os.path.join(out, f"img_{i+1:02d}{ext}")
                open(p, "wb").write(rr.content)
                got.append(os.path.basename(p))
        except Exception:
            continue
        time.sleep(0.4)
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

    steps, ok, files = [], False, []
    for name, fn in (("yt-dlp", try_ytdlp), ("gallery-dl", try_gallerydl), ("scrape", try_scrape)):
        good, log, fs = fn(url, out)
        steps.append({"tool": name, "ok": bool(good), "log": log})
        files = fs
        if good:
            ok = True
            break

    real = []
    for f in os.listdir(out):
        p = os.path.join(out, f)
        if os.path.isfile(p):
            real.append({"name": f, "bytes": os.path.getsize(p), "sha256": sha256(p)})

    meta = {
        "source_url": url,
        "platform_folder": folder,
        "status": "ok" if ok else "failed",
        "tool_used": next((s["tool"] for s in steps if s["ok"]), None),
        "steps": steps,
        "files": real,
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "素材仅供研究/参考/二次创作底稿，勿直接搬运发布",
    }
    json.dump(meta, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return meta


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
                print(f"[{'OK ' if m['status']=='ok' else 'FAIL'}] "
                      f"{m['platform_folder']:<16} {m['source_url'][:70]} "
                      f"-> {len(m['files'])} files")

    lines = ["# 最近一次中继下载", "",
             f"时间：{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}  ",
             f"任务：{len(results)} 条，成功：{sum(1 for m in results if m['status']=='ok')} 条", "",
             "| 平台 | 结果 | 工具 | 文件数 | 体积 | 链接 |", "|---|---|---|---|---|---|"]
    for m in results:
        size = sum(f["bytes"] for f in m["files"])
        lines.append(f"| {m['platform_folder']} | {'✅' if m['status']=='ok' else '❌'} | "
                     f"{m['tool_used'] or '-'} | {len(m['files'])} | {size/1048576:.2f} MB | "
                     f"{m['source_url'][:60]} |")
    lines += ["", "## 逐条明细", ""]
    for m in results:
        lines += [f"### {m['source_url']}", "",
                  f"- 平台目录：`{m['platform_folder']}`",
                  f"- 状态：{m['status']}，命中工具：{m['tool_used'] or '无'}"]
        for f in m["files"]:
            lines.append(f"- `{f['name']}` — {f['bytes']:,} 字节")
        for s in m["steps"]:
            if not s["ok"]:
                lines.append(f"- ❌ {s['tool']}：`{s['log'][:200]}`")
        lines.append("")
    open(os.path.join(RAW, "_LAST_RUN.md"), "w", encoding="utf-8").write("\n".join(lines))
    json.dump(results, open(os.path.join(RAW, "_last_run.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n".join(lines[:14]))


if __name__ == "__main__":
    sys.exit(main())
