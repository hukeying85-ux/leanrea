#!/usr/bin/env python3
"""Download a public Xiaohongshu note in GitHub Actions, failing closed.

The runner verifies the short-link destination and uses five image identifiers
observed on the rendered public note. Every image must decode and pass size and
deduplication checks before the complete batch is published. No login, access
control bypass, or generic page-asset fallback is used.
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
NOTE_ID = "6ad212fc000000001802d6be"
# Five unique image IDs from the visible 1/5 carousel of the public note,
# in its displayed order. The rendered page contains duplicates from carousel
# preloading, which were deduplicated by ID; avatars/comments are excluded.
IMAGE_IDS = (
    "1040g3k8326cqvueoka905qlghp0l1h01fu7131o",
    "1040g3k8326cqvueoka705qlghp0l1h01pro2cso",
    "1040g3k8326cqvueoka7g5qlghp0l1h01cjj2jlg",
    "1040g3k8326cqvueoka805qlghp0l1h01pb66us8",
    "1040g3k8326cqvueoka8g5qlghp0l1h01pt7kqn0",
)
DEST = Path("healing-comic/deliverables/xhs-sunset/originals")
PAGE_DOMAINS = ("xhslink.cn", "xhslink.com", "xiaohongshu.com", "xiaohongshu.cn", "rednote.com")
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
            host = re.sub(r"[^a-zA-Z0-9.:-]", "?", parts.hostname or "")[:120]
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
    except json.JSONDecodeError as exc:
        raise ValueError(f"Note state is not JSON ({exc.msg}, position {exc.pos})") from exc
    if not isinstance(state, dict):
        raise ValueError("Note state is not an object")
    # Regional page versions nest the note differently. Search only structured
    # note objects with the expected title and an explicit imageList.
    matches, stack = [], [state]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            title = node.get("title") or node.get("displayTitle") or ""
            if isinstance(title, str) and EXPECTED_TITLE in title and isinstance(node.get("imageList"), list):
                matches.append((title, node["imageList"]))
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    if len(matches) != 1:
        raise ValueError(f"Expected one matching note with an image list; found {len(matches)}")
    title, images = matches[0]
    if not 1 <= len(images) <= 30:
        raise ValueError("Unexpected number of note images")
    return title, images


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
    _, final_url = fetch(session, SOURCE, PAGE_DOMAINS, 8 * 1024 * 1024)
    if NOTE_ID not in urlsplit(final_url).path:
        raise ValueError("Short link no longer resolves to the expected note")
    # Prior successful xhs-relay jobs used the rendered page's image list and
    # tried the native CDN and image conversion endpoints on the runner.
    # Unlike those jobs, this fails closed if any of the five files is missing.
    title = "和你一起奔夕阳 噜噜噜妹壁纸"
    session.headers.update({"Referer": "https://www.xiaohongshu.com/", "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"})
    records, hashes = [], set()
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=DEST.parent) as temporary:
        temp = Path(temporary)
        for index, image_id in enumerate(IMAGE_IDS, 1):
            token = f"notes_pre_post/{image_id}"
            candidates = (
                ("native", f"https://sns-img-bd.xhscdn.com/{token}"),
                ("png", f"https://ci.xiaohongshu.com/{token}?imageView2/format/png"),
            )
            variants, failures = [], []
            for variant, url in candidates:
                try:
                    content, _ = fetch(session, url, IMAGE_DOMAINS, MAX_IMAGE_BYTES)
                    ext, size = validate(content)
                    variants.append((size[0] * size[1], len(content), variant == "native", content, ext, size, variant))
                except (requests.RequestException, ValueError, OSError) as exc:
                    code = exc.response.status_code if isinstance(exc, requests.HTTPError) and exc.response is not None else type(exc).__name__
                    failures.append(f"{variant}:{code}")
            if not variants:
                raise ValueError(f"Image {index} could not be downloaded or validated ({', '.join(failures)})")
            _, _, _, data, ext, size, variant = max(variants, key=lambda item: item[:3])
            digest = hashlib.sha256(data).hexdigest()
            if digest in hashes:
                raise ValueError("Duplicate image detected; aborting rather than publishing an incomplete set")
            hashes.add(digest)
            name = f"{index:02d}.{ext}"
            (temp / name).write_bytes(data)
            records.append({"file": name, "width": size[0], "height": size[1], "bytes": len(data), "sha256": digest, "variant": variant})
        (temp / "manifest.json").write_text(json.dumps({"source": SOURCE, "note_id": NOTE_ID, "title": title, "image_list_source": "Public note carousel, verified from rendered page; five unique images", "note": "Best validated CDN variant by pixel count; original uncompressed quality is not guaranteed.", "images": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
