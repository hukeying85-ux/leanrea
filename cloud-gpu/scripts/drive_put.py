#!/usr/bin/env python3
"""Stream a local file or JSON bundle to a pre-authorized Google Drive resumable session_uri."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def upload_resumable(session_uri: str, file_path: str, mime_type: str = "application/octet-stream") -> dict:
    total = os.path.getsize(file_path)
    chunk_size = 8 * 1024 * 1024  # 32 * 256 KiB (multiple of 256 KiB per Scotty spec)
    offset = 0
    last_headers: dict[str, str] = {}
    last_body = ""

    with open(file_path, "rb") as f:
        while offset < total or total == 0:
            buf = f.read(chunk_size)
            is_final = (offset + len(buf)) >= total
            cmd = "upload, finalize" if is_final else "upload"
            headers = {
                "Content-Type": mime_type,
                "Content-Length": str(len(buf)),
                "X-Goog-Upload-Offset": str(offset),
                "X-Goog-Upload-Command": cmd,
                "X-Goog-Upload-Total-Size": str(total),
            }
            if total > 0:
                headers["Content-Range"] = f"bytes {offset}-{offset + len(buf) - 1}/{total}"

            req = urllib.request.Request(session_uri, data=buf, headers=headers, method="PUT")
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    last_headers = dict(resp.headers.items())
                    last_body = resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                if exc.code == 308:
                    last_headers = dict(exc.headers.items())
                else:
                    body = exc.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"Drive PUT failed at offset {offset} (HTTP {exc.code}): {body}") from exc

            offset += len(buf)
            if total == 0:
                break

    meta = {}
    if last_body.strip().startswith("{"):
        try:
            meta = json.loads(last_body)
        except json.JSONDecodeError:
            pass
    return {
        "ok": True,
        "bytes": total,
        "upload_status": last_headers.get("X-Goog-Upload-Status", "final"),
        "file_id": meta.get("id"),
        "name": meta.get("name"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Upload file to Google Drive resumable URI.")
    ap.add_argument("--uri-env", required=True, help="Environment variable holding session_uri")
    ap.add_argument("--file", required=True, help="Local file path to upload")
    ap.add_argument("--mime", default="application/json")
    args = ap.parse_args()

    uri = os.environ.get(args.uri_env, "").strip()
    if not uri:
        raise RuntimeError(f"Environment variable {args.uri_env} is empty")
    res = upload_resumable(uri, args.file, args.mime)
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
