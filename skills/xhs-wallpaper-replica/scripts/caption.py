#!/usr/bin/env python3
"""给 1440×3200 的干净壁纸压一组纪念日文字（脚本写字，不交给生图模型）。

用法：
  python3 scripts/caption.py SPEC --in 无字版目录 --out 有字版目录 [--format png|jpg]

SPEC 里新增 "caption" 段（全局默认）+ 每页可覆盖 ty / tone：
  "caption": {
    "line1": "yf ♥ wsh",            # 手写英文行，♥ 用 WenKai 的 U+2665 单独上色
    "line2": "走过你的朝朝暮暮",      # 主句（毛笔楷书 MaShanZheng）
    "line3": "两个月纪念日",          # 小字（LXGW WenKai）
    "ty": 0.37,                      # 文字块中心在画面高度的比例（避开顶部时钟 y≈10–17%）
    "tone": "auto"                   # auto / light / dark：auto 按文字区域亮度选深色字或浅色字
  }
页面级："ty": 0.5, "tone": "dark" 等。

输入目录里的文件名应为 <prefix>NN-<name>.png（phone_mockup build 的输出），输出同名。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

FONT_DIR = Path.home() / ".fonts"
F_SCRIPT = FONT_DIR / "GreatVibes-Regular.ttf"
F_BRUSH = FONT_DIR / "MaShanZheng-Regular.ttf"
F_CJK = FONT_DIR / "LXGWWenKai-Medium.ttf"

PINK = (238, 96, 118)
LIGHT_FG = (255, 250, 245)
DARK_FG = (118, 62, 76)


def load(path, size):
    return ImageFont.truetype(str(path), size)


def text_w(font, s):
    b = font.getbbox(s)
    return b[2] - b[0], b


def render_line1(s, size, fg):
    """英文手写行；'♥' 用 WenKai 心形单独画成粉红。返回 RGBA 图层。"""
    parts = re.split(r"(♥|❤)", s)
    fs = load(F_SCRIPT, size)
    fh = load(F_CJK, int(size * 0.62))
    gap = int(size * 0.16)
    items = []
    for p in parts:
        if not p:
            continue
        if p in ("♥", "❤"):
            items.append(("heart", fh))
        else:
            items.append((p, fs))
    W = sum((text_w(f, "♥" if t == "heart" else t)[0]) for t, f in items) + gap * (len(items) - 1)
    H = int(size * 1.6)
    layer = Image.new("RGBA", (W + 40, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x = 20
    base = int(size * 1.0)
    for t, f in items:
        if t == "heart":
            w, b = text_w(f, "♥")
            # 心形垂直对齐到英文 x-height 中线
            d.text((x - b[0], base - int(size * 0.33) - (b[3] + b[1]) // 2), "♥", font=f, fill=PINK)
        else:
            w, b = text_w(f, t)
            d.text((x - b[0], base), t, font=f, fill=fg, anchor="ls")
        x += w + gap
    return layer


def render_text(s, font, fg, pad=20, spacing=0):
    if spacing:
        # 简单字距：逐字画
        widths = [text_w(font, ch)[0] for ch in s]
        W = sum(widths) + spacing * (len(s) - 1) + pad * 2
        asc, desc = font.getmetrics()
        H = asc + desc + pad * 2
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        x = pad
        for ch, w in zip(s, widths):
            d.text((x, pad), ch, font=font, fill=fg)
            x += w + spacing
        return layer
    b = font.getbbox(s)
    W = b[2] - b[0] + pad * 2
    asc, desc = font.getmetrics()
    H = asc + desc + pad * 2
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((pad - b[0], pad), s, font=font, fill=fg)
    return layer


def halo(layer, radius, color, alpha):
    """给图层做一圈柔光/阴影：用 alpha 通道模糊后上色。"""
    a = layer.split()[3].filter(ImageFilter.GaussianBlur(radius))
    a = a.point(lambda v: min(255, int(v * alpha)))
    h = Image.new("RGBA", layer.size, color + (0,))
    h.putalpha(a)
    return h


def paste_center(canvas, layer, cx, cy, shadow_color, shadow_alpha, shadow_r, offset=(0, 0)):
    x = int(cx - layer.width / 2)
    y = int(cy - layer.height / 2)
    # 扩边后再做光晕，避免被裁
    padded = Image.new("RGBA", (layer.width + shadow_r * 6, layer.height + shadow_r * 6), (0, 0, 0, 0))
    padded.paste(layer, (shadow_r * 3, shadow_r * 3))
    h = halo(padded, shadow_r, shadow_color, shadow_alpha)
    canvas.alpha_composite(h, (x - shadow_r * 3 + offset[0], y - shadow_r * 3 + offset[1]))
    canvas.alpha_composite(padded, (x - shadow_r * 3, y - shadow_r * 3))


def region_lum(img, cx, cy, w, h):
    box = (max(0, int(cx - w / 2)), max(0, int(cy - h / 2)), min(img.width, int(cx + w / 2)), min(img.height, int(cy + h / 2)))
    g = img.convert("L").crop(box)
    return ImageStat.Stat(g).mean[0]


def caption_one(img, cap):
    W, H = img.size
    s = W / 1440.0
    cx = W / 2
    cy = cap.get("ty", 0.37) * H
    tone = cap.get("tone", "auto")
    lum = region_lum(img, cx, cy, 1100 * s, 460 * s)
    if tone == "auto":
        tone = "dark" if lum < 135 else "light"   # dark = 深色背景 → 用浅色字
    if tone == "dark":
        fg, sh, sh_a, sh_r = LIGHT_FG, (40, 20, 40), 0.9, int(14 * s)
    else:
        fg, sh, sh_a, sh_r = DARK_FG, (255, 250, 245), 1.0, int(22 * s)

    size1 = int(cap.get("size1", 190) * s)
    size2 = int(cap.get("size2", 118) * s)
    size3 = int(cap.get("size3", 50) * s)
    l1 = render_line1(cap.get("line1", ""), size1, fg) if cap.get("line1") else None
    l2 = render_text(cap["line2"], load(F_BRUSH, size2), fg, spacing=int(6 * s)) if cap.get("line2") else None
    l3 = render_text(cap["line3"], load(F_CJK, size3), fg, spacing=int(10 * s)) if cap.get("line3") else None

    # 竖向排版：按各图层实际高度（去掉透明边）
    def tight(layer):
        bb = layer.getbbox()
        return layer.crop(bb) if bb else layer

    layers = [tight(l) for l in (l1, l2, l3) if l is not None]
    gaps = [int(g * s) for g in cap.get("gaps", [36, 34])]
    total = sum(l.height for l in layers) + sum(gaps[: len(layers) - 1])
    y = cy - total / 2
    canvas = img.convert("RGBA")
    for i, layer in enumerate(layers):
        paste_center(canvas, layer, cx, y + layer.height / 2, sh, sh_a, sh_r)
        y += layer.height + (gaps[i] if i < len(gaps) else 0)
    return canvas.convert("RGB"), tone, lum


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", type=Path)
    ap.add_argument("--in", dest="indir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--format", choices=["png", "jpg"], default="png")
    a = ap.parse_args()
    spec = json.loads(a.spec.read_text(encoding="utf-8"))
    cap_default = spec.get("caption", {})
    prefix = spec.get("prefix", "")
    os.makedirs(a.out, exist_ok=True)
    for page in spec["pages"]:
        n = page["n"]
        name = f"{prefix}{n:02d}-{page['name']}"
        src = None
        for ext in ("png", "jpg"):
            p = os.path.join(a.indir, f"{name}.{ext}")
            if os.path.exists(p):
                src = p
                break
        if not src:
            print(f"[caption] missing {name}", file=sys.stderr)
            continue
        cap = dict(cap_default)
        for k in ("ty", "tone", "size1", "size2", "size3", "gaps", "line1", "line2", "line3"):
            if k in page:
                cap[k] = page[k]
        img = Image.open(src)
        out, tone, lum = caption_one(img, cap)
        dst = os.path.join(a.out, f"{name}.{a.format}")
        if a.format == "jpg":
            out.save(dst, quality=92, subsampling=0)
        else:
            out.save(dst, optimize=True)
        print(f"[caption] {name}  ty={cap.get('ty', 0.37)} tone={tone} lum={lum:.0f}")


if __name__ == "__main__":
    main()
