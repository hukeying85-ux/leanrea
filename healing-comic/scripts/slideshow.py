#!/usr/bin/env python3
"""slideshow.py —— 把 spec 里的成品页直接拼成轮播视频（SKILL.md E 段的实现）。

配方（与手工 ffmpeg 命令完全一致，只是自动生成滤镜串）：
  每页 scale 到 2160×2880 → zoompan 缓推 z:1→1.06 / 缓拉 1.06→1（奇偶页交替）
  → 输出 1080×1440 @30fps；页间 xfade=fade:duration=0.5
  封面 4s、内容页 4.5s；无音轨（发布时在站内配乐）
  编码 libx264 -crf 21 -pix_fmt yuv420p -movflags +faststart

依赖：imageio-ffmpeg（pip install imageio-ffmpeg）提供 ffmpeg 二进制，
      也可以用 --ffmpeg 指定系统里的 ffmpeg。

用法:
  python3 scripts/slideshow.py --spec runs/素材08-r1/spec.json \\
      --pages runs/素材08-r1/pages --out runs/素材08-r1/video/素材08-r1.mp4
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

W, H = 1080, 1440
FPS = 30
XFADE = 0.5


def ffmpeg_exe(explicit: str | None) -> str:
    if explicit:
        return explicit
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def build(spec: Path, pages: Path, out: Path, cover: float, page: float, crf: int) -> Path:
    items = json.loads(spec.read_text(encoding="utf-8"))
    files = [pages / it.get("out", f"{i:02d}.png") for i, it in enumerate(items, 1)]
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        sys.exit(f"缺少成品页：{missing}")

    durs = [cover] + [page] * (len(files) - 1)
    frames = [int(round(d * FPS)) for d in durs]

    parts, labels = [], []
    for i, (f, d, nf) in enumerate(zip(files, durs, frames)):
        z = "1+0.06*on/%d" % max(1, nf - 1) if i % 2 == 0 else "1.06-0.06*on/%d" % max(1, nf - 1)
        parts.append(
            f"[{i}:v]scale={W*2}:{H*2}:flags=lanczos,"
            f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={nf}:s={W}x{H}:fps={FPS},setsar=1[v{i}]"
        )
        labels.append(f"[v{i}]")

    # xfade 链：offset_k = Σ(dur_0..dur_k) − (k+1)·XFADE
    chain, acc = labels[0], 0.0
    for k in range(1, len(durs)):
        acc += durs[k - 1]
        offset = acc - k * XFADE
        outl = f"[x{k}]"
        parts.append(f"{chain}[v{k}]xfade=transition=fade:duration={XFADE}:offset={offset:.3f}{outl}")
        chain = outl

    filt = ";".join(parts)
    cmd = [ffmpeg_exe(None), "-y"]
    # 每张图只喂一帧，由 zoompan 的 d=nf 负责「复制成 nf 帧」，
    # 这样每段时长严格等于 durs[i]（loop 1 + t 会让 zoompan 成倍放大帧数）
    for f in files:
        cmd += ["-i", str(f)]
    cmd += [
        "-filter_complex", filt, "-map", chain,
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart",
        "-t", f"{sum(durs) - (len(durs) - 1) * XFADE:.3f}",
        "-an", str(out),
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"[slideshow] {len(files)} pages → {out}  ({sum(durs) - (len(durs)-1)*XFADE:.1f}s)")
    subprocess.run(cmd, check=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cover", type=float, default=4.0)
    ap.add_argument("--page", type=float, default=4.5)
    ap.add_argument("--crf", type=int, default=21)
    ap.add_argument("--ffmpeg", default=None)
    a = ap.parse_args()
    build(Path(a.spec), Path(a.pages), Path(a.out), a.cover, a.page, a.crf)


if __name__ == "__main__":
    main()
