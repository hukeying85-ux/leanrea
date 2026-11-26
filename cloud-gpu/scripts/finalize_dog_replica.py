#!/usr/bin/env python3
"""Finish the dog-walk replica so it matches the source clip's exact container & audio specs.

Takes the 25-frame 576x1024 SVD-XT clip (`dog_walk_raw.mp4`) and resamples it to the
source clip's exact geometry, timeline, colorimetry, and bit-identical audio track:
  * 576x1024 -> 544x960 (Lanczos + subtle micro-detail unsharp)
  * 10 fps -> 30 fps motion-compensated interpolation (`minterpolate=mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1`),
    trimmed to exact 73 frames (2.433s)
  * HEVC (`hvc1`) yuv420p, `bt709` colorimetry, ~2000 kb/s matching original
  * Audio: bit-exact AAC 44.1 kHz mono stream-copied (`-c:a copy`) from source `.mp4`
  * Also generates labelled side-by-side comparison `.mp4` and 5-frame temporal contact sheet `.jpg`.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

import imageio_ffmpeg
from PIL import Image, ImageDraw

FF = imageio_ffmpeg.get_ffmpeg_exe()


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr[-4000:] + "\n")
        raise SystemExit(f"ffmpeg failed: {' '.join(cmd[:6])}...")


def probe(path: pathlib.Path) -> dict:
    proc = subprocess.run([FF, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    return {"report": proc.stderr}


def draw_badge(im: Image.Image, text: str) -> Image.Image:
    out = im.copy()
    draw = ImageDraw.Draw(out)
    w_box = max(110, 12 * len(text) + 20)
    draw.rectangle([12, 12, 12 + w_box, 48], fill=(18, 18, 18))
    draw.text((22, 22), text, fill=(255, 235, 130))
    return out


def build_side_by_side_mp4(source: pathlib.Path, replica: pathlib.Path, compare_out: pathlib.Path) -> None:
    """Build side-by-side comparison MP4 without depending on optional libfreetype `drawtext` in static ffmpeg."""
    import cv2
    import numpy as np

    cap_s = cv2.VideoCapture(str(source))
    cap_r = cv2.VideoCapture(str(replica))
    frames_rgb: list[bytes] = []
    idx = 0
    while True:
        ok_s, fs = cap_s.read()
        ok_r, fr = cap_r.read()
        if not ok_s and not ok_r:
            break
        if not ok_s:
            break
        if not ok_r:
            fr = last_fr
        last_fr = fr
        im_s = draw_badge(Image.fromarray(cv2.cvtColor(fs, cv2.COLOR_BGR2RGB)), f"Original (f={idx:02d})")
        im_r = draw_badge(Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)), f"Kaggle Replica (f={idx:02d})")
        w, h = im_s.size
        im_r = im_r.resize((w, h), Image.LANCZOS)
        pair = Image.new("RGB", (w * 2 + 8, h), (24, 24, 24))
        pair.paste(im_s, (0, 0))
        pair.paste(im_r, (w + 8, 0))
        frames_rgb.append(np.asarray(pair, dtype=np.uint8).tobytes())
        idx += 1
    cap_s.release()
    cap_r.release()

    pw, ph = w * 2 + 8, h
    proc = subprocess.Popen(
        [
            FF,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{pw}x{ph}",
            "-r",
            "30",
            "-i",
            "-",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(compare_out),
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None and proc.stderr is not None
    for b in frames_rgb:
        proc.stdin.write(b)
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="replace")
    if proc.wait() != 0:
        raise RuntimeError(f"compare ffmpeg failed: {err[-500:]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="SVD output mp4 (25f @ 576x1024)")
    ap.add_argument("--source", required=True, help="original clip (geometry + audio donor)")
    ap.add_argument("--out", required=True, help="final replica mp4")
    ap.add_argument("--compare", default="", help="optional side-by-side mp4")
    ap.add_argument("--sheet", default="", help="optional comparison contact sheet jpg")
    args = ap.parse_args()

    raw, source, out = pathlib.Path(args.raw), pathlib.Path(args.source), pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 1) Geometry + motion-compensated 30fps 73-frame interpolation + HEVC hvc1 bt709 + bit-exact AAC audio
    run(
        [
            FF,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(raw),
            "-i",
            str(source),
            "-filter_complex",
            "[0:v]scale=544:960:flags=lanczos,"
            "unsharp=3:3:0.35:3:3:0.0,"
            "minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
            "tpad=stop_mode=clone:stop_duration=0.15,"
            "trim=end_frame=73,setpts=N/30/TB[v]",
            "-map",
            "[v]",
            "-map",
            "1:a:0",
            "-c:v",
            "libx265",
            "-preset",
            "medium",
            "-b:v",
            "2000k",
            "-x265-params",
            "colorprim=bt709:transfer=bt709:colormatrix=bt709",
            "-pix_fmt",
            "yuv420p",
            "-tag:v",
            "hvc1",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
            "-color_range",
            "tv",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(out),
        ]
    )

    if args.compare:
        build_side_by_side_mp4(source, out, pathlib.Path(args.compare))

    if args.sheet:
        import cv2

        frame_indices = [0, 18, 36, 54, 71]
        times = [idx / 30.0 for idx in frame_indices]
        rows = []
        for label, path in (("Original (Ground Truth)", source), ("Kaggle GPU + AI Replica", out)):
            cap = cv2.VideoCapture(str(path))
            all_frs = []
            while True:
                ok, fr = cap.read()
                if not ok:
                    break
                all_frs.append(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
            cap.release()
            strip = [
                Image.fromarray(all_frs[min(idx, len(all_frs) - 1)]).resize((272, 480), Image.LANCZOS)
                for idx in frame_indices
            ]
            rows.append((label, strip))
        pad, head = 8, 34
        sheet = Image.new("RGB", (pad + 5 * (272 + pad), head + 2 * (480 + pad + head)), (24, 24, 24))
        draw = ImageDraw.Draw(sheet)
        for i, t in enumerate(times):
            draw.text((pad + i * (272 + pad) + 4, 8), f"t={t:.2f}s (f={frame_indices[i]})", fill=(235, 235, 235))
        for r, (label, strip) in enumerate(rows):
            y = head + r * (480 + pad + head) + 22
            draw.text((pad + 4, y - 22), label, fill=(255, 214, 90))
            for i, im in enumerate(strip):
                sheet.paste(im, (pad + i * (272 + pad), y))
        sheet.save(args.sheet, quality=92)

    print(
        json.dumps(
            {
                "out": str(out),
                "bytes": out.stat().st_size,
                "probe": probe(out)["report"][-1200:],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
