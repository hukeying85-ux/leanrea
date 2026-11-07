#!/usr/bin/env python3
"""grid_preview.py —— 一套多页成品 → 一张「总预览图」（发布前给客户/自己过一眼用）。

和其他脚本一样只依赖 Pillow 与一个中文 .ttf：
  python3 scripts/grid_preview.py --pages runs/素材08-r1/pages --out runs/素材08-r1/preview.jpg \\
      --title "肉呆去广告 · 手机上的广告一根线关掉" --subtitle "10 页成品 · 素材08 第 1 轮" \\
      --font /tmp/LXGWWenKai-Regular.ttf --cols 5

页序按文件名排序（素材08_01.png … 素材08_10.png），只取 .png。
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CREAM = (245, 241, 232)
INK = (50, 21, 13)
MUTED = (122, 106, 99)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--font", required=True)
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--thumb-w", type=int, default=420)
    ap.add_argument("--gap", type=int, default=36)
    ap.add_argument("--margin", type=int, default=72)
    a = ap.parse_args()

    files = sorted(p for p in Path(a.pages).glob("*.png"))
    if not files:
        raise SystemExit("没有找到成品页")
    cols = min(a.cols, len(files))
    rows = (len(files) + cols - 1) // cols
    probe = Image.open(files[0])
    tw = a.thumb_w
    th = round(tw * probe.height / probe.width)
    cap_h = 52
    head = 168 if (a.title or a.subtitle) else a.margin

    W = a.margin * 2 + cols * tw + (cols - 1) * a.gap
    H = head + rows * (th + cap_h) + (rows - 1) * a.gap + a.margin // 2
    sheet = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(sheet)
    f_title = ImageFont.truetype(a.font, 64)
    f_sub = ImageFont.truetype(a.font, 34)
    f_cap = ImageFont.truetype(a.font, 26)

    if a.title:
        d.text((a.margin, a.margin - 10), a.title, font=f_title, fill=INK)
    if a.subtitle:
        d.text((a.margin, a.margin + 72), a.subtitle, font=f_sub, fill=MUTED)

    for i, p in enumerate(files):
        r, c = divmod(i, cols)
        x = a.margin + c * (tw + a.gap)
        y = head + r * (th + cap_h + a.gap)
        im = Image.open(p).convert("RGB").resize((tw, th), Image.LANCZOS)
        sheet.paste(im, (x, y))
        d.rectangle([x, y, x + tw - 1, y + th - 1], outline=(225, 217, 205))
        d.text((x + 4, y + th + 10), f"{i + 1:02d}", font=f_cap, fill=MUTED)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=92)
    print(f"[grid_preview] {len(files)} pages → {out}  ({sheet.width}×{sheet.height})")


if __name__ == "__main__":
    main()
