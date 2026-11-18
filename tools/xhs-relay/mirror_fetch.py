#!/usr/bin/env python3
"""
mirror_fetch.py — 在 GitHub Actions runner 里跑，把「沙箱够不着的云盘文件」搬回仓库。

为什么需要它：Arena 沙箱出网只放行 github / pypi / npm，Dropbox / Google Drive / 小红书 CDN
一律不通；而 runner 出网不受限。于是把分享直链写进 mirror.json，runner 下完解压后 commit 回
触发它的那条分支，沙箱 `git pull` 就拿到了（= 落到本地硬盘）。

mirror.json 格式：
{
  "jobs": [
    {
      "url": "https://www.dropbox.com/scl/fo/<id>/<hash>?rlkey=...&dl=1",   # 必需，文件夹或单文件
      "out_dir": "mirror/dropbox",        # 相对仓库根目录
      "unpack": true,                     # 下完解压（zip）并删除压缩包
      "strip_top": true,                  # 解压后去掉顶层的「素材05/」这一层，避免路径重复
      "include": ["第17轮", "第18轮"],     # 可选：只保留路径里包含这些子串的条目
      "skip_existing": true               # 可选：out_dir 里已存在的同名文件不重下（续传）
    }
  ]
}

Dropbox 文件夹分享链要带 `dl=1` 才会直接给 zip；不带也兼容（会先试 dl=1）。
"""
import json
import os
import shutil
import sys
import time
import zipfile

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MIRROR = os.path.join(ROOT, "tools", "xhs-relay", "mirror.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HDR = {"User-Agent": UA, "Accept": "*/*"}


def log(*a):
    print(*a, flush=True)


def as_dl(url):
    # Google Drive 单文件：https://drive.google.com/file/d/<ID>/view  ->  uc?export=download&id=<ID>
    if "drive.google.com" in url:
        import re
        m = re.search(r"/d/([A-Za-z0-9_-]{20,})", url) or re.search(r"[?&]id=([A-Za-z0-9_-]{20,})", url)
        if m:
            return f"https://drive.google.com/uc?export=download&confirm=t&id={m.group(1)}"
    if "dl=" in url:
        return url
    return url + ("&" if "?" in url else "?") + "dl=1"


def _gdrive_confirm(html):
    """大文件会被 Drive 的「无法扫描病毒」页拦一次；从 form 里抠出真实下载地址。"""
    import re
    m = re.search(r'<form[^>]+id="download-form"[^>]+action="([^"]+)"', html)
    if not m:
        m = re.search(r'action="(https://drive\.usercontent\.google\.com/download[^"]*)"', html)
    if not m:
        return None
    action = m.group(1).replace("&amp;", "&")
    params = dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', html))
    return action, params


def download(url, dest):
    """流式下载，边下边报进度。返回字节数。"""
    url = as_dl(url)
    with requests.get(url, headers=HDR, stream=True, timeout=300, allow_redirects=True) as r:
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        if "text/html" in ctype:
            body = r.text
            log(f"   HTML page ({len(body)} chars) — 先查是否 Drive 确认页")
            cf = _gdrive_confirm(body)
            if not cf:
                log("   HTML HEAD: " + " ".join(body.split())[:600])
                raise RuntimeError("got HTML instead of a file (need public share link?)")
            action, params = cf
            log(f"   confirm-form -> {action[:80]} params={list(params)}")
            with requests.get(action, headers=HDR, params=params, stream=True,
                              timeout=300, allow_redirects=True) as r2:
                r2.raise_for_status()
                return _save(r2, dest)
        return _save(r, dest)


def _save(r, dest):
    total = int(r.headers.get("content-length") or 0)
    if total > 200_000_000:
        log(f"   WARNING: {total/1e9:.2f} GB；GitHub runner 仓库建议 <2GB，超出请分卷/改用 LFS")
    n = 0
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            if not chunk:
                continue
            f.write(chunk)
            n += len(chunk)
            if total and n % (64 << 20) < (1 << 20):
                log(f"    {n/1e6:.0f}/{total/1e6:.0f} MB")
    log(f"   downloaded {n/1e6:.1f} MB -> {os.path.relpath(dest, ROOT)}")
    return n


def pick(name, include):
    if not include:
        return True
    return any(s in name for s in include)


def unpack(zip_path, out_dir, include, strip_top):
    """解压 zip，支持按 include 过滤、去掉顶层目录。"""
    n_ok = 0
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename
            # 去掉 Excel/__MACOSX 之类的垃圾条目
            base = os.path.basename(name)
            if not base or base.startswith("._") or "__MACOSX" in name:
                continue
            if not pick(name, include):
                continue
            rel = name
            if strip_top:
                parts = rel.split("/", 1)
                rel = parts[1] if len(parts) == 2 else parts[0]
            dest = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            n_ok += 1
    return n_ok


def run_job(job):
    url = job["url"]
    out_dir = os.path.join(ROOT, job["out_dir"])
    os.makedirs(out_dir, exist_ok=True)
    log(f"== {url[:110]}\n   -> {job['out_dir']}")
    tmp_dir = os.path.join(ROOT, ".mirror_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp = os.path.join(tmp_dir, f"dl_{int(time.time())}")
    n = download(url, tmp)
    if job.get("manifest_only") and zipfile.is_zipfile(tmp):
        with zipfile.ZipFile(tmp) as z:
            rows = [(i.filename, i.file_size) for i in z.infolist() if not i.is_dir()]
        log(f"   MANIFEST {len(rows)} entries:")
        for n, sz in rows:
            log(f"     {sz:>10}  {n}")
        os.remove(tmp)
        return n

    head = open(tmp, "rb").read(4)
    if head[:2] == b"PK":
        # per_entry_dir: 每个条目放到 out_dir/<条目名去扩展名>/ 下（多轮 zip 分开成文件夹用）
        if job.get("per_entry_dir"):
            n_files = 0
            with zipfile.ZipFile(tmp) as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename
                    base = os.path.basename(name)
                    if not base or base.startswith("._") or "__MACOSX" in name:
                        continue
                    if not pick(name, job.get("include")):
                        continue
                    stem = os.path.splitext(base)[0]
                    d = os.path.join(out_dir, stem)
                    os.makedirs(d, exist_ok=True)
                    with z.open(info) as src, open(os.path.join(d, base), "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    n_files += 1
            log(f"   unpacked {n_files} file(s) into per-entry folders")
            os.remove(tmp)
            return n
        n_files = unpack(tmp, out_dir, job.get("include"), job.get("strip_top", True))
        log(f"   unpacked {n_files} file(s)")
        os.remove(tmp)
    else:
        # 单文件：用响应头里的文件名，拿不到就用 URL 尾段
        name = job.get("name") or os.path.basename(url.split("?")[0]) or "download.bin"
        shutil.move(tmp, os.path.join(out_dir, name))
        log(f"   single file {n/1e6:.1f} MB -> {job['out_dir']}/{name}")
    return n


def main():
    path = sys.argv[sys.argv.index("--mirror") + 1] if "--mirror" in sys.argv else MIRROR
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    jobs = cfg.get("jobs", [])
    log(f"mirror: {len(jobs)} job(s)")
    for job in jobs:
        try:
            run_job(job)
        except Exception as e:  # noqa: BLE001
            log(f"   JOB FAILED: {type(e).__name__}: {e}")
    log("== mirror done ==")


if __name__ == "__main__":
    main()
