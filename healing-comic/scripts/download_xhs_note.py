#!/usr/bin/env python3
"""Download a public Xiaohongshu note in GitHub Actions, failing closed.

Only the supplied short link is used. The page must contain a matching note
and an image list; every image must decode and pass size/deduplication checks.
No login, bypass of access controls, or generic og:image fallback is used.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from PIL import Image

SOURCE = "https://xhslink.cn/o/5thkO8Kd6jg"
EXPECTED_TITLE = "和你一起奔夕阳"
DEST = Path("healing-comic/deliverables/xhs-sunset/originals")
PAGE_DOMAINS = ("xhslink.cn", "xhslink.com", "xiaohongshu.com", "xiaohongshu.cn")
IMAGE_DOMAINS = ("xhscdn.com", "xiaohongshu.com", "xiaohongshu.cn")
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def allowed_url(url: str, domains: tuple[str, ...]) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return (parts.scheme == "https" and not parts.username and not parts.password
            and parts.port in (None, 443)
            and any(host == domain or host.endswith("." + domain) for domain in domains))


def fetch(session: requests.Session, url: str, domains: tuple[str, ...], limit: int) -> tuple[bytes, str]:
    for _ in range(8):
        if not allowed_url(url, domains):
            parts = urlsplit(url)
            host = re.sub(r"[^a-zA-Z0-9.:-]", "?", parts.netloc)[:120]
            raise ValueError(f"Blocked redirect or URL outside the expected domains ({parts.scheme}://{host})")
        with session.get(url, timeout=(15, 45), stream=True, allow_redirects=False) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers["Location"])
                continue
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > limit:
                    raise ValueError("Response too large")
                chunks.append(chunk)
            return b"".join(chunks), url
    raise ValueError("Too many redirects")


def parse_note(html: str) -> tuple[str, list[dict]]:
    # Do not evaluate JavaScript from the remote site. Decode only its JSON state.
    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*", html)
    if not match:
        raise ValueError("Page did not contain a readable note state (login or verification may be required)")
    raw = html[match.end():]
    raw = re.sub(r"\bundefined\b", "null", raw)
    try:
        state, _ = json.JSONDecoder().raw_decode(raw.lstrip())
        notes = state["note"]["noteDetailMap"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("Unable to parse note data safely") from exc
    matches = []
    for entry in notes.values():
        note = entry.get("note", {}) if isinstance(entry, dict) else {}
        title = note.get("title", "") or ""
        if EXPECTED_TITLE in title and isinstance(note.get("imageList"), list):
            matches.append(note)
    if len(matches) != 1:
        raise ValueError("Expected exactly one matching note with an image list")
    note = matches[0]
    images = note["imageList"]
    if not 1 <= len(images) <= 30:
        raise ValueError("Unexpected number of note images")
    return note["title"], images


def image_url(image: dict) -> str:
    # These are the note's own image entries, not arbitrary page assets.
    candidates = [image.get("originImageUrl"), image.get("urlDefault")]
    for info in image.get("infoList", []):
        if isinstance(info, dict) and info.get("imageScene") in ("WB_DFT", "WB_PRV"):
            candidates.append(info.get("url"))
    for url in candidates:
        if isinstance(url, str) and allowed_url(url, IMAGE_DOMAINS):
            return url
    raise ValueError("Note image has no supported CDN URL")


def validate(data: bytes) -> tuple[str, tuple[int, int]]:
    if len(data) < 10_000:
        raise ValueError("Image response is too small")
    with Image.open(io.BytesIO(data)) as im:
        fmt, size = im.format, im.size
        if fmt not in {"JPEG", "PNG", "WEBP"} or min(size) < 350 or max(size) > 15000:
            raise ValueError(f"Unexpected image format or dimensions: {fmt} {size}")
        im.verify()
    with Image.open(io.BytesIO(data)) as im:
        im.load()  # Verify full decode, not just headers.
    return {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[fmt], size


def main() -> None:
    if DEST.exists():
        raise FileExistsError(f"Output already exists, not overwriting: {DEST}")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5"})
    page, _ = fetch(session, SOURCE, PAGE_DOMAINS, 8 * 1024 * 1024)
    title, images = parse_note(page.decode("utf-8", errors="replace"))
    records, hashes = [], set()
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=DEST.parent) as temporary:
        temp = Path(temporary)
        for index, image in enumerate(images, 1):
            data, _ = fetch(session, image_url(image), IMAGE_DOMAINS, MAX_IMAGE_BYTES)
            ext, size = validate(data)
            digest = hashlib.sha256(data).hexdigest()
            if digest in hashes:
                raise ValueError("Duplicate image detected; aborting rather than publishing an incomplete set")
            hashes.add(digest)
            name = f"{index:02d}.{ext}"
            (temp / name).write_bytes(data)
            records.append({"file": name, "width": size[0], "height": size[1], "bytes": len(data), "sha256": digest})
        (temp / "manifest.json").write_text(json.dumps({"source": SOURCE, "title": title, "note": "Images returned by the public page; original uncompressed quality is not guaranteed.", "images": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        shutil.move(str(temp), DEST)
    print(f"Validated {len(records)} images from: {title}")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "unknown"
        print(f"::error::Remote service returned HTTP {code}; no images were saved.")
        raise SystemExit(1)
    except requests.RequestException as exc:
        print(f"::error::Network request failed ({type(exc).__name__}); no images were saved.")
        raise SystemExit(1)
    except (ValueError, FileExistsError) as exc:
        print(f"::error::{exc}; no new images were saved.")
        raise SystemExit(1)
