#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把配图统一成"单墨双色版画"（duotone），解决风格打架的问题。

为什么要这一步：
    一套课件里同时出现写实照片、3D 渲染、水彩插画、风景照，视觉上是"四种材料拼起来"。
    生物学教材真正统一的视觉语言是**单色版画/铜版画**：一张纸，一种墨。
    把所有配图压到"深松墨 + 暖纸"两个色阶，混合媒介立刻读成同一套图版。

用法：
    python3 scripts/duotone.py <原图目录> <输出目录> [--width 1600]

输出两个版本：
    <name>-light.jpg   浅版：纸底浅、墨色深，用于浅色页的整版图/半版图
    <name>-ink.jpg     深版：墨底、亮部收窄，用于深色页叠加文字
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

PAPER = (244, 239, 228)
INK = (20, 48, 47)
INK_DEEP = (11, 24, 25)
INK_SOFT = (86, 108, 100)


def duotone(img: Image.Image, low: tuple, high: tuple, contrast=1.25, gamma=1.0) -> Image.Image:
    g = ImageOps.grayscale(img)
    g = ImageOps.autocontrast(g, cutoff=1)
    g = ImageEnhance.Contrast(g).enhance(contrast)
    if gamma != 1.0:
        g = g.point(lambda v: int(255 * (v / 255.0) ** gamma))
    return ImageOps.colorize(g, black=low, white=high)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--width", type=int, default=1600)
    a = ap.parse_args()

    src, dst = Path(a.src), Path(a.dst)
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(src.glob("*.jpg")) + sorted(src.glob("*.png")):
        img = Image.open(f).convert("RGB")
        if img.width > a.width:
            img = img.resize((a.width, round(img.height * a.width / img.width)), Image.LANCZOS)
        light = duotone(img, INK, PAPER, contrast=1.15, gamma=0.58)
        ink = duotone(img, INK_DEEP, INK_SOFT, contrast=1.1)
        light.save(dst / f"{f.stem}-light.jpg", quality=86, optimize=True)
        ink.save(dst / f"{f.stem}-ink.jpg", quality=86, optimize=True)
        n += 2
    print(f"[ok] {n} 张（{n // 2} 组 light/ink）→ {dst}")


if __name__ == "__main__":
    main()
