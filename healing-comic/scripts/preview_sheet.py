#!/usr/bin/env python3
"""将一批独立图片合成为一张带编号的总预览；保留完整画面，不修改原图。

用法：python3 preview_sheet.py /path/to/images --output /path/to/预览.jpg
依赖：Pillow。按文件名开头的数字排序，仅收集以数字开头的 PNG/JPEG/WebP 图片。
不会覆盖已有的预览文件；如需重新生成，请指定新文件名。
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    sys.exit("需要 Pillow：python3 -m pip install Pillow")


def make_sheet(files: list[Path], output: Path, columns: int = 5) -> Path:
    if not files:
        raise ValueError("没有找到可用图片")
    if columns < 1:
        raise ValueError("列数必须大于 0")
    if output.exists():
        raise FileExistsError(f"预览已存在，请指定新文件名：{output}")
    if output.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        raise ValueError("输出文件扩展名须为 jpg、jpeg 或 png")
    columns = min(columns, len(files))
    rows = math.ceil(len(files) / columns)
    width, height, gap, padding, footer = 320, 430, 18, 24, 34
    sheet = Image.new("RGB", (padding * 2 + columns * width + (columns - 1) * gap,
                              padding * 2 + rows * (height + footer) + (rows - 1) * gap), "#f7f1e6")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    for i, path in enumerate(files):
        x = padding + (i % columns) * (width + gap)
        y = padding + (i // columns) * (height + footer + gap)
        draw.rectangle((x, y, x + width - 1, y + height + footer - 1), fill="white")
        with Image.open(path) as source:
            thumb = ImageOps.contain(ImageOps.exif_transpose(source).convert("RGB"),
                                     (width, height), method=Image.Resampling.LANCZOS)
        sheet.paste(thumb, (x + (width - thumb.width) // 2, y + (height - thumb.height) // 2))
        number = re.match(r"\d+", path.stem)
        label = number.group() if number else f"{i + 1:02d}"
        draw.text((x + width // 2, y + height + footer // 2), label,
                  fill="#51372d", font=font, anchor="mm")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=94) if output.suffix.lower() in (".jpg", ".jpeg") else sheet.save(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=5)
    args = parser.parse_args()
    files = sorted((p for p in args.directory.iterdir()
                    if p.is_file() and re.match(r"\d", p.name)
                    and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                    and p.resolve() != args.output.resolve()),
                   key=lambda p: (int(re.match(r"\d+", p.name).group()), p.name))
    try:
        output = make_sheet(files, args.output, args.columns)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"预览生成失败：{exc}\n")
    print(f"已生成 {len(files)} 张图片的总预览：{output}")


if __name__ == "__main__":
    main()
