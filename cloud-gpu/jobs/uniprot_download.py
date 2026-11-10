#!/usr/bin/env python3
"""从 Kaggle 下载 UniProt（Swiss-Prot 细菌胞质蛋白）并回传私有 Drive。

用法（在 Kaggle kernel 内由 gpu-relay 调用）：
    python _payload.py fasta     # 下载 FASTA.gz 并上传
    python _payload.py tsv       # 下载 TSV.gz  并上传

设计要点：
  * 查询式与 DualAMP-Lite 快照 2026-11-10 完全一致（见 uniprot_query.txt）；
  * 只做下载 + 校验 + 回传，不做任何数据库合并 / 训练；
  * 分块 PUT 到预授权 resumable URI（DRIVE_UPLOAD_URI），文件名与大小由上行方决定，
    因此不会覆盖 Drive 上已有文件（每次调用方都新建带时间戳的文件夹）；
  * 校验：gzip 完整性、记录数、sha256、md5。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

QUERY = (
    "(reviewed:true) AND (taxonomy_id:2) AND (cc_scl_term:SL-0086) "
    "AND (length:[100 TO 5000]) AND (NOT ft_signal:*) AND (NOT ft_transmem:*)"
)

TSV_FIELDS = "accession,id,protein_name,organism_name,length,cc_subcellular_location"

TARGETS = {
    "fasta": {
        "params": {"query": QUERY, "format": "fasta", "compressed": "true"},
        "name": "uniprot_bacteria_cytoplasm_reviewed.fasta.gz",
        "mime": "application/gzip",
    },
    "tsv": {
        "params": {"query": QUERY, "format": "tsv", "compressed": "true", "fields": TSV_FIELDS},
        "name": "uniprot_bacteria_cytoplasm_reviewed.tsv.gz",
        "mime": "application/gzip",
    },
}

STREAM_URL = "https://rest.uniprot.org/uniprotkb/stream"
CHUNK = 8 * 1024 * 1024  # 32 x 256 KiB


def log(msg: str) -> None:
    print(msg, flush=True)


def download(params: dict, dest: str, attempts: int = 4) -> dict:
    url = f"{STREAM_URL}?{urllib.parse.urlencode(params)}"
    last_err = None
    for i in range(1, attempts + 1):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dualamp-lite/4.0 (+gpu-relay)"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
                total = 0
                while True:
                    buf = resp.read(1 << 20)
                    if not buf:
                        break
                    fh.write(buf)
                    total += len(buf)
            log(f"download attempt {i}: {total} bytes in {time.time() - t0:.1f}s")
            if total == 0:
                raise RuntimeError("empty response body")
            return {"attempts": i, "bytes": total, "seconds": round(time.time() - t0, 1), "url": STREAM_URL}
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            log(f"download attempt {i} failed: {type(exc).__name__}: {exc}")
            if i < attempts:
                time.sleep(10 * i)
    raise RuntimeError(f"download failed after {attempts} attempts: {last_err}")


def validate(kind: str, path: str) -> dict:
    with gzip.open(path, "rb") as fh:  # raises on corrupt stream
        gz_ok = True
        if kind == "fasta":
            records = sum(1 for line in fh if line.startswith(b">"))
            first = last = None
            fh.seek(0)
            for line in fh:
                if line.startswith(b">"):
                    acc = line[1:].split(b"|")[1].decode() if b"|" in line[:40] else line[1:].split()[0].decode()
                    if first is None:
                        first = acc
                    last = acc
        else:
            header = fh.readline().decode("utf-8", "replace").rstrip("\n")
            records = sum(1 for _ in fh)
            first = last = None
    out = {"gzip_ok": gz_ok, "records": records}
    if kind == "fasta":
        out["first_accession"] = first
        out["last_accession"] = last
    else:
        out["header"] = header
    return out


def digests(path: str) -> dict:
    sha, md5, size = hashlib.sha256(), hashlib.md5(), 0
    with open(path, "rb") as fh:
        while True:
            buf = fh.read(1 << 20)
            if not buf:
                break
            size += len(buf)
            sha.update(buf)
            md5.update(buf)
    return {"size_bytes": size, "sha256": sha.hexdigest(), "md5": md5.hexdigest()}


def upload(session_uri: str, path: str, mime: str) -> dict:
    total = os.path.getsize(path)
    offset = 0
    last_headers: dict[str, str] = {}
    last_body = ""
    with open(path, "rb") as f:
        while True:
            buf = f.read(CHUNK)
            if not buf:
                break
            is_final = offset + len(buf) >= total
            headers = {
                "Content-Type": mime,
                "Content-Length": str(len(buf)),
                "X-Goog-Upload-Offset": str(offset),
                "X-Goog-Upload-Command": "upload, finalize" if is_final else "upload",
                "X-Goog-Upload-Total-Size": str(total),
                "Content-Range": f"bytes {offset}-{offset + len(buf) - 1}/{total}",
            }
            req = urllib.request.Request(session_uri, data=buf, headers=headers, method="PUT")
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    last_headers = dict(resp.headers.items())
                    last_body = resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as exc:
                if exc.code == 308:
                    last_headers = dict(exc.headers.items())
                else:
                    raise
            offset += len(buf)
    meta = {}
    if last_body.strip().startswith("{"):
        try:
            meta = json.loads(last_body)
        except json.JSONDecodeError:
            pass
    return {"bytes_sent": offset, "upload_status": last_headers.get("X-Goog-Upload-Status"),
            "file_id": meta.get("id"), "name": meta.get("name")}


def main() -> int:
    kind = (sys.argv[1] if len(sys.argv) > 1 else "fasta").lower()
    if kind not in TARGETS:
        raise SystemExit(f"unknown target {kind!r}; expected one of {sorted(TARGETS)}")
    spec = TARGETS[kind]
    out_dir = "/kaggle/working" if os.path.isdir("/kaggle/working") else "."
    dest = os.path.join(out_dir, spec["name"])

    summary: dict = {
        "script": "uniprot_download",
        "target": kind,
        "query": QUERY,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version.split()[0],
    }
    try:
        summary["download"] = download(spec["params"], dest)
        summary["validation"] = validate(kind, dest)
        summary["digests"] = digests(dest)
        uri = os.environ.get("DRIVE_UPLOAD_URI", "").strip()
        if uri:
            summary["upload"] = upload(uri, dest, spec["mime"])
        else:
            summary["upload"] = {"skipped": "DRIVE_UPLOAD_URI not set"}
    except Exception as exc:  # noqa: BLE001
        import traceback

        summary["fatal"] = f"{type(exc).__name__}: {exc}"
        summary["traceback"] = traceback.format_exc()[-3000:]
    summary["finished_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    blob = json.dumps(summary, ensure_ascii=False, indent=2)
    log(blob)
    with open(os.path.join(out_dir, f"uniprot_{kind}_summary.json"), "w", encoding="utf-8") as fh:
        fh.write(blob + "\n")
    return 0 if "fatal" not in summary else 1


if __name__ == "__main__":
    raise SystemExit(main())
