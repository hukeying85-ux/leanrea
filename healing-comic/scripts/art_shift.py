#!/usr/bin/env python3
"""art_shift.py —— 底图垂直微调（不重画，只挪位置）。

用途：生图模型给的底图常常把角色画得偏高，合成时中幅点题句（x ≈ 0.568）
会压在角色脸上。这个脚本把底图整体下移 N 像素、顶部补暖纸色，
再裁回 1080×1447，让「标签 → 上半场气泡 → 点题句 → 下半场气泡」四段
结构与底图的净区对齐。可反复调 --dy，不消耗生图次数。

用法:
  python3 scripts/art_shift.py --src runs/素材08-r1/art --out runs/素材08-r1/art-fit \\
      --dy 100 --skip 01.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

W, H = 1080, 1447
CREAM = (245, 241, 232)


def shift(src: Path, dst: Path, dy: int) -> None:
    im = Image.open(src).convert("RGB")
    scale = W / im.width
    im = im.resize((W, max(1, round(im.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), CREAM)
    canvas.paste(im, (0, dy))
    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dy", type=int, default=100, help="正数=下移")
    ap.add_argument("--skip", nargs="*", default=[], help="不处理的文件名")
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    n = 0
    for f in sorted(src.glob("*.png")):
        if f.name in a.skip:
            continue
        shift(f, out / f.name, a.dy)
        n += 1
    print(f"[art_shift] {n} files -> {out} (dy={a.dy})")


if __name__ == "__main__":
    main()
