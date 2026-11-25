#!/usr/bin/env python3
"""给「祝福文字 新年壁纸」的干净底图脚本压竖排毛笔祝福语。

模型只画纸、花枝和空白卡片；所有汉字、红色印章都由本脚本画上去，
所以 10 张可以各自换文案，不会让生图模型写错字。

用法：
  python3 scripts/newyear_caption.py SPEC --in 无字版目录 --out 有字版目录 \
      --art-dir 底稿目录 [--format png|jpg]
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path.home() / ".fonts"
# Ma Shan Zheng 好看但缺 20 个常用繁体字（萬/順/歲/氣/財…），整句会出现方框；
# 霞鹜文楷覆盖完整且本身就是楷书/手写味道，改为它，再对笔画做轻微膨胀模拟毛笔。
F_BRUSH = FONT_DIR / "LXGWWenKai-Medium.ttf"
F_CJK = FONT_DIR / "LXGWWenKai-Medium.ttf"
RED = (166, 50, 44)
INK = (28, 26, 24)
PAPER = (250, 245, 232)


def font(path, size):
    return ImageFont.truetype(str(path), max(1, int(size)))


def find_page(out_dir, prefix, n, fmt):
    hits = sorted(out_dir.glob(f"{prefix}{n:02d}-*.{fmt}"))
    if not hits:
        raise FileNotFoundError(f"{out_dir}/{prefix}{n:02d}-*.{fmt}")
    return hits[0]


def cover_map(art_size, canvas):
    """复现 phone_mockup.fit_canvas 的 cover 裁切，返回 (sx, sy, scale)。"""
    aw, ah = art_size
    W, H = canvas
    scale = max(W / aw, H / ah)
    return (W - aw * scale) / 2, (H - ah * scale) / 2, scale


def mapped_box(box, art_size, canvas):
    sx, sy, scale = cover_map(art_size, canvas)
    x0, y0, x1, y1 = box
    aw, ah = art_size
    W, H = canvas
    return (
        max(W * 0.02, sx + x0 * aw * scale),
        max(H * 0.02, sy + y0 * ah * scale),
        min(W * 0.98, sx + x1 * aw * scale),
        min(H * 0.98, sy + y1 * ah * scale),
    )


def draw_card(img, box):
    """半透明奶油色卡片 + 柔和投影，覆盖底图里那块空白纸条。"""
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((x0 + 8, y0 + 10, x1 + 8, y1 + 10), radius=6,
                        fill=(70, 55, 40, 55))
    d.rectangle((x0, y0, x1, y1), fill=PAPER + (232,))
    img.alpha_composite(layer)


def draw_vertical(img, text, box, f_size, ink=INK, shadow=True):
    x0, y0, x1, y1 = box
    cx = (x0 + x1) / 2
    top = y0 + (y1 - y0) * 0.10
    usable = (y1 - y0) * 0.74
    chars = list(text)
    step = usable / max(1, len(chars) - 1)
    f = font(F_BRUSH, f_size)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, ch in enumerate(chars):
        cy = top + i * step
        b = f.getbbox(ch)
        x = cx - (b[2] - b[0]) / 2 - b[0]
        y = cy - (b[3] - b[1]) / 2 - b[1]
        if shadow:
            off = max(3, int(f_size * 0.10))
            d.text((x + off, y + off), ch, font=f, fill=(90, 82, 72, 130))
        d.text((x, y), ch, font=f, fill=ink + (255,))
    # 轻微膨胀 = 楷书笔画带一点毛笔的厚重感
    a = layer.split()[3].filter(ImageFilter.MaxFilter(3))
    layer.putalpha(a)
    img.alpha_composite(layer)


def draw_seal(img, box, char):
    x0, y0, x1, y1 = box
    w = x1 - x0
    s = int(w * 0.30)
    cx = (x0 + x1) / 2
    cy = y1 - s * 0.75
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2),
                        radius=int(s * 0.08), fill=RED + (235,))
    f = font(F_BRUSH, s * 0.72)
    b = f.getbbox(char)
    d.text((cx - (b[2] - b[0]) / 2 - b[0], cy - (b[3] - b[1]) / 2 - b[1]),
           char, font=f, fill=(252, 244, 232, 255))


def draw_side(img, text, box):
    x0, y0, x1, y1 = box
    W, H = img.size
    x = max(int(W * 0.025), int(x0 - (x1 - x0) * 0.75))
    y = y0 + (y1 - y0) * 0.04
    f = font(F_CJK, W * 0.017)
    d = ImageDraw.Draw(img)
    for ch in text:
        b = f.getbbox(ch)
        d.text((x - b[0], y - b[1]), ch, font=f, fill=(72, 62, 54, 220))
        y += (b[3] - b[1]) + W * 0.008


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--art-dir", required=True)
    ap.add_argument("--format", choices=["png", "jpg"], default="png")
    a = ap.parse_args()

    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    W, H = spec.get("canvas", [1888, 4096])
    prefix = spec.get("prefix", "祝福")
    src, out, art_dir = Path(a.src), Path(a.out), Path(a.art_dir)
    out.mkdir(parents=True, exist_ok=True)

    for pg in spec["pages"]:
        n = pg["n"]
        src_path = find_page(src, prefix, n, a.format)
        art_path = sorted(art_dir.glob(f"{n:02d}.*"))[0]
        art_size = Image.open(art_path).size
        img = Image.open(src_path).convert("RGBA")

        lbox = mapped_box(pg["card_left"], art_size, (W, H))
        rbox = mapped_box(pg["card_right"], art_size, (W, H))
        draw_card(img, lbox)
        draw_card(img, rbox)

        fs = min((lbox[2] - lbox[0]) * 0.80, (lbox[3] - lbox[1]) * 0.19)
        draw_vertical(img, pg["left"], lbox, fs)
        draw_vertical(img, pg["right"], rbox, fs * 0.98)
        draw_seal(img, lbox, pg.get("seal", "福"))
        draw_seal(img, rbox, pg.get("seal2", "喜"))
        draw_side(img, pg.get("side", ""), lbox)

        dest = out / src_path.name
        if a.format == "jpg":
            img.convert("RGB").save(dest, quality=94)
        else:
            img.save(dest)
        print("[text]", src_path.name, pg["left"], "/", pg["right"])


if __name__ == "__main__":
    main()
