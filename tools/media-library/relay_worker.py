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
import shutil
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

# 完整浏览器请求头：B站那层 WAF 认的是 sec-ch-ua / sec-fetch-* 这套，
# 光有 User-Agent 会被判成脚本直接 412
BROWSER_H = {
    "User-Agent": UA,
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,image/apng,*/*;q=0.8"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


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
# 优先用 nightly：YouTube 的 extractor 每周都在被修，正式版经常跟不上
YT_BIN = shutil.which("yt-dlp-nightly") or shutil.which("yt-dlp") or "yt-dlp"

YT_BASE = [YT_BIN, "--no-warnings", "--no-playlist", "--ignore-errors",
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
            clients = ["android_vr", "web_safari,mweb", "ios,mweb",
                       "tv,web_embedded", "default,-web_safari"]
            extra = f"youtube:player_client={clients[i % len(clients)]}"
            if i >= len(clients):
                # 再退一步：接受缺 PO token 的格式，有时候能直接下下来
                extra += ";formats=missing_pot"
            cmd += ["--extractor-args", extra]
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


def _safe_json(t):
    try:
        json.loads(t)
        return True
    except Exception:
        return False


def _dbg(path, text):
    """沙箱读不到 Actions 日志（日志存在 azure，出口被墙），
    所以把诊断信息写成文件，跟素材一起 commit 到 media-out，本地 git 就能看。"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(str(text) + "\n")
    except Exception:
        pass


def _extract_initial_state(html):
    """XHS 把笔记数据塞在 window.__INITIAL_STATE__={...} 里。
    用花括号配平（会跳过字符串里的括号）把它整段抠出来，
    不能简单正则到第一个 </script> —— 那样 JSON 会被截断、解析必失败。"""
    key = "window.__INITIAL_STATE__"
    i = html.find(key)
    if i < 0:
        return ""
    k = html.find("{", i)
    if k < 0:
        return ""
    depth, in_str, esc = 0, False, False
    for m in range(k, len(html)):
        c = html[m]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return html[k:m + 1]
    return ""


BAD_IMG = ("fe-static", "/as/v2/", ".js", ".css", "avatar", "icon")


def _xhs_urls_from_html(html):
    """从小红书笔记页里把整组原图 URL 抠出来。返回顺序 = 图片顺序。"""
    html = html.replace("\\u002F", "/").replace("\\/", "/")
    state = _extract_initial_state(html)
    hay = state or html

    urls = []
    # 1) 结构化：note.noteDetailMap.<id>.note.images_list[].infoList[]（多档清晰度）
    if state:
        try:
            data = json.loads(state)
            notes = ((data.get("note") or {}).get("noteDetailMap") or {})
            for _, nv in (notes.items() if isinstance(notes, dict) else []):
                note = (nv or {}).get("note") or nv or {}
                lst = note.get("images_list") or note.get("imageList") or []
                for im in lst:
                    best, best_score = None, -1
                    for info in (im.get("infoList") or []):
                        u = info.get("url")
                        if not u:
                            continue
                        w = info.get("width") or 0
                        sc = info.get("imageScene") or ""
                        score = (3 if sc == "WB_DFT" else 0) + (2 if w >= 1000 else 0) + (1 if w >= 600 else 0)
                        if score > best_score:
                            best, best_score = u, score
                    u = best or im.get("urlDefault") or im.get("urlPre")
                    if u:
                        urls.append(u)
        except Exception:
            urls = []

    # 2) 兜底：直接从 __INITIAL_STATE__ 文本里扫图链（结构变了也还能用）
    if not urls:
        # 小红书 JSON 里常见协议相对地址 //sns-webpic-qc.xhscdn.com/...，别漏
        cand = re.findall(r'(?:https?:)?//[^"\s\\<>]+?xhscdn\.com/[^"\s\\<>]+', hay)
        cand += re.findall(r'(?:https?:)?//[^"\s\\<>]+?xiaohongshu\.com/spectrum/[^"\s\\<>]+', hay)
        cand = [("https:" + c if c.startswith("//") else c) for c in cand]
        urls = [u for u in cand if not any(b in u for b in BAD_IMG)]

    # 3) 还不行就退回整页
    if not urls:
        cand = re.findall(r'(?:https?:)?//[^"\s\\<>]+?xhscdn\.com/[^"\s\\<>]+', html)
        cand = [("https:" + c if c.startswith("//") else c) for c in cand]
        urls = [u for u in cand if not any(b in u for b in BAD_IMG)]

    # 按图片 ID 去重（同一张图的多档清晰度路径相同、后缀不同）
    out, seen = [], set()
    for u in urls:
        key = re.sub(r"[!?].*$", "", u).rstrip("/").split("/")[-1]
        if key and key not in seen:
            seen.add(key)
            out.append(u)
    return out


BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

def _seo_headers(referer="https://www.google.com/"):
    """小红书 guestBrowsePolicy 只对 seo / direct 来源放行，
    从自己站内跳过去（Referer: xiaohongshu.com）会拿到游客壳。
    所以伪装成「从 Google 点进来」。"""
    return {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": referer,
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
    }


def _images_from_any_json(obj, out):
    """从小红书任意一份 JSON 里挖图片 URL：feed API / INITIAL_STATE 都吃。"""
    found = []

    def walk(node):
        if isinstance(node, dict):
            # feed API: items[].note_card.image_list[].{url_default,info_list}
            if "info_list" in node or "infoList" in node:
                lst = node.get("info_list") or node.get("infoList") or []
                best, score = None, -1
                for it in lst:
                    u = it.get("url") or it.get("url_default")
                    if not u:
                        continue
                    w = it.get("width") or 0
                    sc = it.get("image_scene") or it.get("imageScene") or ""
                    sc2 = (3 if sc in ("WB_DFT", "WB_PRV") else 0) + (2 if w >= 1000 else 0)
                    if sc2 > score:
                        best, score = u, sc2
                if best:
                    found.append(best)
            if "url_default" in node and isinstance(node.get("url_default"), str):
                found.append(node["url_default"])
            if "urlDefault" in node and isinstance(node.get("urlDefault"), str):
                found.append(node["urlDefault"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(obj)
    for u in found:
        if u and not any(b in u for b in BAD_IMG) and (("xhscdn" in u) or ("spectrum" in u)):
            out.append(u)
    return out


def _clean_xhs(u):
    u = u.replace("\\/", "/").replace("http://", "https://")
    u = re.sub(r"!nd_dft\w+", "", u)
    u = re.sub(r"\?imageView2/.*$", "", u)
    u = re.sub(r"\?imageMogr2/.*$", "", u)
    return u


def _dedupe_keep_order(urls):
    out, seen = [], set()
    for u in urls:
        key = re.sub(r"[!?].*$", "", u).rstrip("/").split("/")[-1]
        if key and key not in seen:
            seen.add(key)
            out.append(u)
    return out


# --------------------------------------------------------------------------
# 0. 小红书首选：JoeanAmier/XHS-Downloader（GitHub 12.9k star）
#    用 curl_cffi 做浏览器 TLS 指纹伪装，2.2 版起官方说明「无需 cookie」即可取原图
# --------------------------------------------------------------------------
XHSDL_REPO = "https://github.com/JoeanAmier/XHS-Downloader"
XHSDL_DIR = "/tmp/xhsdl"
XHSDL_OUT = "/tmp/xhsdl_dl"

XHSDL_SCRIPT = r"""
import asyncio, json, os, sys
sys.path.insert(0, "%s")
os.chdir("%s")
from source import XHS

FULL = dict(work_path="%s", folder_name="Download", name_format="作品ID",
            impersonate="chrome146", cookie="", proxy=None, timeout=20,
            chunk=1024 * 1024 * 10, max_retry=3, avg_delay=0.5,
            record_data=False, image_format="AUTO", folder_mode=True,
            image_download=True, video_download=False,
            video_cover_download=False, live_download=False,
            download_record=False, language="zh_CN", author_archive=False,
            write_mtime=False, note_format="")
MINIMAL = dict(work_path="%s", folder_name="Download", cookie="",
               timeout=20, image_format="AUTO", folder_mode=True,
               image_download=True, video_download=False,
               download_record=False)


async def main():
    url = sys.argv[1]
    try:
        x = XHS(**FULL)
    except TypeError as e:
        print("kwargs trimmed: %%s" %% e)
        x = XHS(**MINIMAL)
    async with x as xhs:
        data = await xhs.extract(url, True)
    if not isinstance(data, dict):
        data = {"raw": str(data)}
    json.dump(data, open("/tmp/xhs_detail.json", "w", encoding="utf-8"),
              ensure_ascii=False, default=str)
    print("detail keys: %%s" %% list(data.keys())[:20])


asyncio.run(main())
""" % (XHSDL_DIR, XHSDL_DIR, XHSDL_OUT, XHSDL_OUT)


def _ensure_xhs_downloader(DBG):
    """把 XHS-Downloader 源码与依赖装到 /tmp（runner 每次都是干净的）"""
    if not os.path.isdir(os.path.join(XHSDL_DIR, "source")):
        rc, out = run(["git", "clone", "--depth", "1", XHSDL_REPO, XHSDL_DIR], timeout=300)
        _dbg(DBG, "[clone] rc=%s %s" % (rc, out[-300:]))
        if rc != 0:
            return False
    req = os.path.join(XHSDL_DIR, "requirements.txt")
    if os.path.isfile(req):
        rc, out = run([sys.executable, "-m", "pip", "install", "-q",
                       "--disable-pip-version-check", "-r", req], timeout=900)
        _dbg(DBG, "[pip] rc=%s %s" % (rc, out[-400:]))
    return True


def try_xhs_downloader(url, out):
    """调用 XHS-Downloader 的 extract()，拿下载地址后自己下原图。"""
    DBG = os.path.join(RAW, "_debug", "xhs_dl_%s.txt" % os.path.basename(out))
    _dbg(DBG, "=== xhs-downloader %s ===" % url)
    if not _ensure_xhs_downloader(DBG):
        return False, "xhs-downloader: 源码没装好", []

    shutil.rmtree(XHSDL_OUT, ignore_errors=True)
    os.makedirs(XHSDL_OUT, exist_ok=True)
    if os.path.exists("/tmp/xhs_detail.json"):
        os.remove("/tmp/xhs_detail.json")
    script = "/tmp/xhsdl_run.py"
    open(script, "w", encoding="utf-8").write(XHSDL_SCRIPT)
    rc, log = run([sys.executable, script, url], timeout=600)
    _dbg(DBG, "[run] rc=%s\n%s" % (rc, log[-2500:]))

    # 1) 它自己下好的文件
    got = []
    for rel in list_files_recursive(XHSDL_OUT):
        p = os.path.join(XHSDL_OUT, rel)
        if not os.path.isfile(p) or os.path.getsize(p) < 5000:
            continue
        ext = os.path.splitext(rel)[1].lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
            continue
        shutil.copy(p, os.path.join(out, "xhs_%02d%s" % (len(got) + 1, ".jpg"
                                                          if ext == ".heic" else ext)))
        got.append(rel)
    _dbg(DBG, "tool downloaded: %d -> %s" % (len(got), got[:20]))

    # 2) 从返回的详情里再抠一遍直链，按原图规格自己下（双保险）
    detail = {}
    if os.path.exists("/tmp/xhs_detail.json"):
        try:
            detail = json.load(open("/tmp/xhs_detail.json", encoding="utf-8"))
        except Exception as e:
            _dbg(DBG, "detail json bad: %s" % e)
    raw = json.dumps(detail, ensure_ascii=False)
    cands = re.findall(r'https?://[^"\s\\<>\']+', raw)
    cands = [u for u in cands
             if ("xhscdn" in u or "spectrum" in u)
             and not any(b in u for b in BAD_IMG)]
    cands = _dedupe_keep_order([_clean_xhs(u) for u in cands])
    _dbg(DBG, "detail urls: %d" % len(cands))
    for u in cands[:20]:
        _dbg(DBG, "   %s" % u[:170])

    for u in cands[:60]:
        try:
            r = requests.get(u, headers={"User-Agent": BROWSER_UA,
                                         "Referer": "https://www.xiaohongshu.com/"},
                             timeout=60)
            if r.status_code == 200 and len(r.content) > 5000:
                ext = (".jpg" if ("jpeg" in u.lower() or "jpg" in u.lower())
                       else ".png" if "png" in u.lower() else ".webp")
                dst = os.path.join(out, "xhs_%02d%s" % (len(got) + 1, ext))
                open(dst, "wb").write(r.content)
                got.append(os.path.basename(dst))
        except Exception:
            continue
        time.sleep(0.2)
    _dbg(DBG, "TOTAL saved: %d" % len(got))
    return len(got) >= 2, "xhs-downloader: saved %d" % len(got), got


def try_xhs_ultimate(url, out):
    """小红书原图终极通道：能试的路全试一遍，先到先得。

    机房 IP 裸请求只能拿到「游客壳」（guestBrowsePolicy.enabled=true，
    页面里 0 个图链）。已知可行的几种绕法：
      A. 伪装 seo / direct 来源   —— 页面里给的放行名单就是这两个
      B. r.jina.ai 文本代理        —— 第三方抓取，出口不是机房
      C. Wayback Machine 归档     —— 抓别人存档过的页面
      D. Playwright 真浏览器渲染   —— 客户端 JS 会去调 feed API，图片在响应里
    """
    DBG = os.path.join(RAW, "_debug", "xhs_ult_%s.txt" % os.path.basename(out))
    _dbg(DBG, "=== ultimate %s ===" % url)
    urls = []

    # A. seo / direct 来源
    for ref_name, ref in (("seo-google", "https://www.google.com/"),
                          ("seo-bing", "https://www.bing.com/"),
                          ("direct", None)):
        try:
            h = _seo_headers(ref) if ref else _seo_headers()
            h.pop("Referer", None) if ref is None else None
            r = requests.get(url, headers=h, timeout=45)
            st = _extract_initial_state(r.text)
            n_before = len(urls)
            if st:
                obj = None
                for txt in (st, re.sub(r"\bundefined\b", "null", st),
                            re.sub(r",\s*\}", "}", st)):
                    try:
                        obj = json.loads(txt)
                        break
                    except Exception:
                        continue
                if obj is not None:
                    _images_from_any_json(obj, urls)
                else:
                    _dbg(DBG, "     state 不是合法 JSON，退化成文本扫描")
                    urls += _xhs_urls_from_html(r.text)
            _dbg(DBG, "[A/%s] http=%s bytes=%d state=%d urls+%d"
                 % (ref_name, r.status_code, len(r.text), len(st), len(urls) - n_before))
            if st and ref_name == "seo-google":
                for kw in ("images_list", "imageList", "xhscdn", "url_default",
                           "urlDefault", "info_list", "noteDetailMap", "undefined"):
                    _dbg(DBG, "     kw %-14s x%d" % (kw, st.count(kw)))
                _dbg(DBG, "     state tail: %s" % re.sub(r"\s+", " ", st[-500:]))
                _dbg(DBG, "     raw xhscdn in html: %d"
                     % len(re.findall(r"xhscdn", r.text)))
                for _m in list(re.finditer(r"xhscdn", st))[:8]:
                    _lo = max(0, _m.start() - 170)
                    _dbg(DBG, "     ctx> %s" % re.sub(r"\s+", " ", st[_lo:_m.start() + 170]))
        except Exception as e:
            _dbg(DBG, "[A/%s] %s: %s" % (ref_name, type(e).__name__, e))

    # B. r.jina.ai 文本代理
    for proxy in ("https://r.jina.ai/", "https://r.jina.ai/http://"):
        try:
            target = url if proxy.endswith("ai/") else url.replace("https://", "")
            r = requests.get(proxy + target, timeout=90)
            got = re.findall(r"https?://[^\s)\"']+?(?:xhscdn|spectrum)[^\s)\"']*", r.text)
            got = [g for g in got if not any(b in g for b in BAD_IMG)]
            _dbg(DBG, "[B] %s http=%s bytes=%d urls=%d" % (proxy[:24], r.status_code, len(r.text), len(got)))
            for u in got[:12]:
                _dbg(DBG, "     %s" % u[:150])
            urls += got
            if got:
                break
        except Exception as e:
            _dbg(DBG, "[B] %s failed: %s" % (type(e).__name__, e))

    # C. Wayback Machine 归档
    try:
        note_id = re.search(r"/(?:explore|discovery/item)/([0-9a-f]{16,32})", url)
        note_id = note_id.group(1) if note_id else ""
        cdx = ("https://web.archive.org/cdx/search/cdx?url=xiaohongshu.com*%s*"
               "&output=json&limit=10&filter=statuscode:200" % note_id)
        r = requests.get(cdx, timeout=60,
                         headers={"User-Agent": BROWSER_UA})
        snapshots = []
        if r.status_code == 200 and r.text.strip().startswith("["):
            rows = json.loads(r.text)
            snapshots = [(row[1], row[2]) for row in rows[1:] if len(row) > 2]
        _dbg(DBG, "[C] snapshots for %s: %d" % (note_id, len(snapshots)))
        for ts, orig in snapshots[:3]:
            try:
                u2 = "https://web.archive.org/web/%sid_/%s" % (ts, orig)
                r2 = requests.get(u2, timeout=90, headers={"User-Agent": BROWSER_UA})
                got = re.findall(r"https?://[^\s)\"']+?(?:xhscdn|spectrum)[^\s)\"']*", r2.text)
                got = [g for g in got if not any(b in g for b in BAD_IMG)]
                _dbg(DBG, "     snapshot %s http=%s bytes=%d urls=%d" % (ts, r2.status_code, len(r2.text), len(got)))
                urls += got
                if got:
                    break
            except Exception as e:
                _dbg(DBG, "     snapshot %s failed: %s" % (ts, type(e).__name__))
    except Exception as e:
        _dbg(DBG, "[C] wayback failed: %s" % type(e).__name__)

    # D. Playwright 真浏览器（装了才试）
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        _dbg(DBG, "[D] playwright 未安装: %s" % type(e).__name__)
        sync_playwright = None
    if sync_playwright:
        try:
            captured = []
            with sync_playwright() as pw:
                br = pw.chromium.launch(args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
                ctx = br.new_context(locale="zh-CN", user_agent=BROWSER_UA,
                                     viewport={"width": 1440, "height": 900},
                                     extra_http_headers={"Referer": "https://www.google.com/"})
                pg = ctx.new_page()

                def _on_resp(resp):
                    u = resp.url
                    if ("/api/sns/web/v1/feed" in u or "edith.xiaohongshu.com" in u
                            or "/api/sns/web/v2/" in u):
                        try:
                            captured.append(resp.json())
                        except Exception:
                            pass

                pg.on("response", _on_resp)
                pg.goto(url, wait_until="domcontentloaded", timeout=90000)
                pg.wait_for_timeout(6000)
                try:
                    pg.mouse.wheel(0, 1200)
                    pg.wait_for_timeout(3000)
                except Exception:
                    pass
                html_rendered = ""
                try:
                    html_rendered = pg.content()
                except Exception as e:
                    _dbg(DBG, "     [D] content() failed: %s" % type(e).__name__)
                dom_imgs = []
                try:
                    # Vue 的响应式对象带循环引用，直接 stringify 会抛异常 —— 各步单独兜住
                    dom_imgs = pg.eval_on_selector_all(
                        "img",
                        "els => els.map(e => e.currentSrc || e.src || e.dataset.src || '')")
                except Exception as e:
                    _dbg(DBG, "     [D] dom img failed: %s" % type(e).__name__)
                state_txt = ""
                try:
                    state_txt = pg.evaluate(
                        "() => { try { return JSON.stringify(window.__INITIAL_STATE__); }"
                        " catch (e) { return 'ERR:' + e.message; } }")
                except Exception as e:
                    _dbg(DBG, "     [D] state eval failed: %s" % type(e).__name__)
                br.close()
                if html_rendered:
                    _rend = [u for u in re.findall(
                        r'https?://[^"\s\\<>]+?(?:xhscdn|spectrum)[^"\s\\<>]*', html_rendered)
                        if not any(bd in u for bd in BAD_IMG)]
                    _dbg(DBG, "     [D] rendered html urls: %d" % len(_rend))
                    for _u in _rend[:12]:
                        _dbg(DBG, "        %s" % _u[:150])
                    urls += _rend
            _dbg(DBG, "[D] api responses captured: %d | state bytes: %d | dom imgs: %d"
                 % (len(captured), len(state_txt or ""), len(dom_imgs)))
            for u in dom_imgs[:12]:
                _dbg(DBG, "     dom %s" % str(u)[:150])
            for _i, c in enumerate(captured):
                _keys = list(c.keys())[:12] if isinstance(c, dict) else type(c).__name__
                _dbg(DBG, "     api[%d] keys=%s" % (_i, _keys))
                _dbg(DBG, "     api[%d] head=%s" % (_i, json.dumps(c, ensure_ascii=False)[:400]))
                _images_from_any_json(c, urls)
            if state_txt and not state_txt.startswith("ERR:"):
                try:
                    _images_from_any_json(json.loads(state_txt), urls)
                except Exception:
                    pass
            for u in dom_imgs:
                if u and (("xhscdn" in u) or ("spectrum" in u)) and not any(b in u for b in BAD_IMG):
                    urls.append(u)
        except Exception as e:
            _dbg(DBG, "[D] playwright failed: %s: %s" % (type(e).__name__, e))

    cleaned = _dedupe_keep_order([_clean_xhs(u) for u in urls])
    _dbg(DBG, "TOTAL candidate urls: %d" % len(cleaned))
    for u in cleaned[:20]:
        _dbg(DBG, "   %s" % u[:170])

    got = []
    for i, u in enumerate(cleaned[:60]):
        try:
            r = requests.get(u, headers={"User-Agent": BROWSER_UA,
                                         "Referer": "https://www.xiaohongshu.com/"}, timeout=60)
            if r.status_code == 200 and len(r.content) > 5000:
                ext = ".jpg" if ("jpeg" in u.lower() or "jpg" in u.lower()) else (
                    ".png" if "png" in u.lower() else ".webp")
                pth = os.path.join(out, f"xhs_{i+1:02d}{ext}")
                open(pth, "wb").write(r.content)
                got.append(os.path.basename(pth))
        except Exception:
            continue
        time.sleep(0.2)
    _dbg(DBG, "TOTAL saved: %d" % len(got))
    return len(got) >= 2, f"ultimate: {len(cleaned)} candidates, saved {len(got)}", got


# --------------------------------------------------------------------------
# 3. 小红书专用：yt-dlp 能解析页面，只是图片笔记没有 video format
# --------------------------------------------------------------------------
def try_xhs_dump(url, out):
    urls = []

    DBG = os.path.join(RAW, "_debug", "xhs_%s.txt" % os.path.basename(out))
    _dbg(DBG, "=== %s ===" % url)
    _dbg(DBG, "UA: %s" % UA[:60])

    # A. yt-dlp dump（视频笔记能 dump 出来；图片笔记它会直接报错）
    rc, so, se = run([YT_BIN, "--no-warnings", "--no-playlist", "--user-agent", UA,
                      "--dump-single-json", url], timeout=180)
    _dbg(DBG, "yt-dlp rc=%s stdout=%d bytes stderr_tail=%s" % (rc, len(so), (se or "").strip()[-200:]))
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

    # B. 直接解页面里的 __INITIAL_STATE__，拿整组 imageList。
    #    注意：不能只在 yt-dlp 失败时才走 —— yt-dlp 常常只吐出 1 张缩略图就收工，
    #    那样整组图就只剩一张。两条路都跑，再合并去重。
    page_note = ""
    try:
        r = requests.get(url, headers={"User-Agent": UA,
                                       "Accept-Language": "zh-CN,zh;q=0.9",
                                       "Referer": "https://www.xiaohongshu.com/"}, timeout=45)
        html = r.text
        _dbg(DBG, "page GET status=%s bytes=%d" % (r.status_code, len(html)))
        _dbg(DBG, "has __INITIAL_STATE__: %s" % bool(re.search(r"__INITIAL_STATE__", html)))
        _st = _extract_initial_state(html)
        _dbg(DBG, "initial_state bytes: %d" % len(_st))
        _dbg(DBG, "initial_state parses as JSON: %s" % (bool(_st) and _safe_json(_st)))
        _dbg(DBG, "initial_state head: %s" % re.sub(r"\s+", " ", _st[:400]))
        _dbg(DBG, "xhscdn hits in html: %d" % len(re.findall(r"xhscdn", html)))
        _raw = re.findall(r'https?://[^"\s\\<>]+?(?:xhscdn|spectrum)[^"\s\\<>]*', html)
        _dbg(DBG, "raw cdn urls (%d):" % len(_raw))
        for _u in _raw[:30]:
            _dbg(DBG, "   raw %s" % _u[:180])
        _dbg(DBG, "og:image: %s" % re.findall(
            r'<meta[^>]+?(?:og:image|twitter:image)[^>]*?content="([^"]+)"', html)[:10])
        _dbg(DBG, "has cookie header support: %s" % bool(os.environ.get("COOKIES_XHS")))
        _dbg(DBG, "cookie wall: %s" % ("登录" in html or "login" in html.lower()))
        _dbg(DBG, "html head: %s" % re.sub(r"\s+", " ", html[:600]))
        got_urls = _xhs_urls_from_html(html)
        _dbg(DBG, "urls from page: %d" % len(got_urls))
        for u in got_urls[:12]:
            _dbg(DBG, "   %s" % u[:160])
        urls += got_urls
    except Exception as e:
        page_note = f" | page: {type(e).__name__}: {e}"
        _dbg(DBG, "page GET failed: %s" % page_note)
    if not urls:
        return False, f"dump rc={rc} {se.strip()[-160:]}{page_note} | no image urls", []

    if not urls:
        return False, f"dump rc={rc} {se.strip()[-160:]} | no image urls in page", []

    cleaned, seen = [], set()
    for u in urls:
        # 去掉小红书的降质后缀，拿原始大图
        u = re.sub(r"!nd_dft_\w+", "", u)
        u = re.sub(r"\?imageView2/.*$", "", u).replace("\\/", "/")
        u = u.replace("http://", "https://")
        key = re.sub(r"\?.*$", "", u)          # 同一张图的不同参数算同一张
        if key not in seen:
            seen.add(key)
            cleaned.append(u)

    _dbg(DBG, "cleaned urls: %d" % len(cleaned))
    for u in cleaned[:12]:
        _dbg(DBG, "   clean %s" % u[:160])

    got = []
    for i, u in enumerate(cleaned[:60]):
        try:
            r = requests.get(u, headers={"User-Agent": UA, "Referer": "https://www.xiaohongshu.com/"},
                             timeout=60)
            if r.status_code == 200 and len(r.content) > 10000:
                ext = ".jpg" if "jpeg" in u.lower() or "jpg" in u.lower() else (
                    ".png" if "png" in u.lower() else ".webp")
                p = os.path.join(out, f"xhs_{i+1:02d}{ext}")
                open(p, "wb").write(r.content)
                got.append(os.path.basename(p))
                _dbg(DBG, "saved %s (%d bytes, http %s)" % (os.path.basename(p), len(r.content), r.status_code))
        except Exception as e:
            _dbg(DBG, "download failed %s: %s" % (u[:80], type(e).__name__))
            continue
        time.sleep(0.3)

    _dbg(DBG, "TOTAL saved: %d" % len(got))
    # 只拿到 1 张通常说明页面没解析开 —— 别急着收工，让后面的 gallery-dl / scrape 再试
    ok = len(got) >= 2
    return ok, f"dumped {len(cleaned)} urls, saved {len(got)}", got


# --------------------------------------------------------------------------
# 3.5 B站专用：网页端 412（WAF），改走官方 web-interface / playurl 接口
# --------------------------------------------------------------------------
def try_bilibili_api(url, out):
    bv = re.search(r"(BV[0-9A-Za-z]+)", url)
    if not bv:
        return False, "no bvid", []
    bvid = bv.group(1)
    h = dict(BROWSER_H, Referer="https://www.bilibili.com/",
             Origin="https://www.bilibili.com")
    # 多入口轮试：web 接口 / app 接口 / wbi 前的老接口
    endpoints = [
        f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
        f"https://app.bilibili.com/x/v2/view?bvid={bvid}&build=7240300&mobi_app=android",
        f"https://api.bilibili.com/view?type=bvid&bvid={bvid}",
    ]
    v = None
    diag = []
    for ep in endpoints:
        try:
            r = requests.get(ep, headers=h, timeout=30)
            try:
                j = r.json()
            except Exception:
                diag.append(f"{ep.split('/')[2]}: HTTP {r.status_code} non-json")
                continue
            if j.get("code") == 0 and (j.get("data") or {}).get("cid"):
                v = j
                break
            diag.append(f"{ep.split('/')[2]}: code={j.get('code')}")
        except Exception as e:
            diag.append(f"{ep.split('/')[2]}: {type(e).__name__}")
    if not v:
        return False, " | ".join(diag) or "all endpoints blocked", []
    try:
        cid = v["data"]["cid"]
        title = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", v["data"]["title"])[:40]
    except Exception as e:
        return False, f"parse: {e}", []

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
# 3.7 YouTube 专用：Invidious 公共实例 —— 换一条完全不在数据中心 IP 上的路
#     Invidious 是开源 YouTube 前端，它自己的服务器去取流，我们只跟它要结果
# --------------------------------------------------------------------------
INVIDIOUS = [
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://yewtu.be",
    "https://iv.melmac.space",
    "https://invidious.privacyredirect.com",
    "https://invidious.f5.si",
]


def _h(res):
    m = re.search(r"(\d+)", str(res or ""))
    return int(m.group(1)) if m else 0


def try_invidious(url, out):
    vid = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", url)
    if not vid:
        return False, "no 11-char video id", []
    vid = vid.group(1)
    diag = []
    for inst in INVIDIOUS:
        host = inst.split("//")[1]
        try:
            r = requests.get(f"{inst}/api/v1/videos/{vid}",
                             headers={"User-Agent": UA}, timeout=35)
            if r.status_code != 200:
                diag.append(f"{host}: HTTP {r.status_code}")
                continue
            j = r.json()
        except Exception as e:
            diag.append(f"{host}: {type(e).__name__}")
            continue

        prog = [(f.get("resolution"), f.get("url"))
                for f in (j.get("formatStreams") or []) if f.get("url")]
        prog = [p for p in prog if 0 < _h(p[0]) <= 480] or prog
        prog.sort(key=lambda p: -_h(p[0]))

        vids = [(f.get("qualityLabel") or f.get("resolution"), f.get("url"))
                for f in (j.get("adaptiveFormats") or [])
                if f.get("url") and "audio" not in (f.get("type") or "")]
        vids = [v for v in vids if 0 < _h(v[0]) <= 720] or vids
        vids.sort(key=lambda v: -_h(v[0]))

        auds = [(f.get("audioQuality") or f.get("bitrate") or "0", f.get("url"))
                for f in (j.get("adaptiveFormats") or [])
                if f.get("url") and "audio" in (f.get("type") or "")]
        auds.sort(key=lambda a: -int(re.sub(r"\D", "", str(a[0])) or 0))

        title = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", j.get("title") or "yt")[:40]
        final = os.path.join(out, f"{title}_{vid}.mp4")

        def grab(u, dst):
            rr = requests.get(u, headers={"User-Agent": UA, "Referer": inst},
                              timeout=300, stream=True)
            if rr.status_code not in (200, 206):
                return False
            with open(dst, "wb") as f:
                for c in rr.iter_content(1 << 20):
                    f.write(c)
            return os.path.getsize(dst) > 50000

        if prog:
            if grab(prog[0][1], final):
                return True, f"{host}: progressive {prog[0][0]}", [os.path.basename(final)]
            diag.append(f"{host}: progressive download failed")
        if vids:
            vp = os.path.join(out, "v.tmp")
            ap = os.path.join(out, "a.tmp")
            if grab(vids[0][1], vp):
                if auds and grab(auds[0][1], ap):
                    run(["ffmpeg", "-y", "-loglevel", "error", "-i", vp, "-i", ap,
                         "-c", "copy", final], timeout=600)
                else:
                    run(["ffmpeg", "-y", "-loglevel", "error", "-i", vp,
                         "-c", "copy", final], timeout=600)
                for p in (vp, ap):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
                if os.path.exists(final) and os.path.getsize(final) > 50000:
                    return True, f"{host}: adaptive+mux {vids[0][0]}", [os.path.basename(final)]
            diag.append(f"{host}: adaptive download failed")
    return False, " | ".join(diag) or "no invidious instance reachable", []


# --------------------------------------------------------------------------
# 3.8 公共代理中继：B站/抖音对机房 IP 硬拒绝，借第三方代理换个出口 IP 试试
# --------------------------------------------------------------------------
PROXY_TPL = [
    "https://api.codetabs.com/v1/proxy?quest=",
    "https://api.allorigins.win/raw?url=",
    "https://corsproxy.io/?url=",
]


def try_proxy_relay(url, out):
    """只用于拿元数据 JSON（B站 view / playurl、抖音 iteminfo）。"""
    diag = []
    for tpl in PROXY_TPL:
        host = tpl.split("//")[1].split("/")[0]
        try:
            from urllib.parse import quote
            r = requests.get(tpl + quote(url, safe=""),
                             headers={"User-Agent": UA}, timeout=45)
            if r.status_code != 200:
                diag.append(f"{host}: HTTP {r.status_code}")
                continue
            txt = r.text.strip()
            if not txt or txt[0] not in "{[":
                diag.append(f"{host}: non-json {txt[:60]!r}")
                continue
            try:
                j = json.loads(txt)
            except Exception:
                diag.append(f"{host}: json parse failed")
                continue
            json.dump(j, open(os.path.join(out, f"_proxy_{host}.json"), "w",
                              encoding="utf-8"), ensure_ascii=False, indent=2)
            return True, f"{host}: got JSON", []
        except Exception as e:
            diag.append(f"{host}: {type(e).__name__}")
    return False, " | ".join(diag) or "no proxy worked", []


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
    # 视频优先的平台，先换条不在机房 IP 上的路
    if folder == "03_YouTube素材":
        chain.insert(1, ("invidious", try_invidious))
    if folder in ("05_B站素材", "02_抖音素材"):
        chain.append(("proxy-relay", try_proxy_relay))
    if folder == "01_小红书素材":
        # 机房 IP 裸请求只有游客壳，先走终极通道（seo来源/代理/归档/真浏览器），
        # 都失败再退回原来的 dump-json
        chain.insert(0, ("xhs-downloader", try_xhs_downloader))
        chain.insert(1, ("xhs-ultimate", try_xhs_ultimate))
        chain.insert(2, ("xhs-dump", try_xhs_dump))
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
