#!/usr/bin/env python3
"""
card_typeset.py — 给「纯色底 + 可爱大字 + 贴纸」这一类清新壁纸排版中文。

生图模型画中文会出乱码/错字，所以这一类的做法是：
  生图只出**纯色/纸纹底 + 少量英文墨迹**（无中文）→ 本脚本把中文祝福语、落款、
  「鸿运当头」式的英文小字、贴纸小图标全部用字体和矢量图形画上去。

用法：
  python3 scripts/card_typeset.py build SPEC --art-dir ART --out OUT [--format png|jpg]
  python3 scripts/card_typeset.py all   SPEC --art-dir ART --out OUT   # build + 总图 + 封面

spec 里每页可写：
  "card": {
    "title_font": "kuaile" | "mashan",         # 标题字体（默认 kuaile）
    "title_size": 190,                          # 标题字号（按 1440 宽基准）
    "title": "发财被爱\n好运常在",              # 手动分行，\n 换行
    "sub": "Have a nice day",                   # 标题下方英文小字
    "side": "平安喜乐",                         # 竖排落款（右上/右下）
    "side_pos": "right" | "left",
    "seal": "福",                               # 印章字
    "badge": "LUCKY",                           # 底部胶囊小字
    "deco": ["apple", "star", "bear", "coin", "flower", "sparkle", "bow", "arc"],
    "eyebrow": "2026",                          # 标题上方小字
  }
canvas 用 spec.canvas（这一轮 = 原帖 884×1920 等比放大到 1326×2880）。
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CJK = {
    "kuaile": "~/.fonts/ZCOOLKuaiLe-Regular.ttf",
    "mashan": "~/.fonts/MaShanZheng-Regular.ttf",
    "wengkai": "~/.fonts/LXGWWenKai-Medium.ttf",
    "inter": "~/.fonts/Inter-Variable.ttf",
}


def F(kind, size):
    p = Path(CJK[kind]).expanduser()
    if not p.exists():
        sys.exit(f"字体缺失：{p}")
    return ImageFont.truetype(str(p), size)


def text_size(d, t, f):
    b = d.textbbox((0, 0), t, font=f)
    return b[2] - b[0], b[3] - b[1], b


def draw_center(d, t, f, cx, cy, fill, spacing=0):
    if spacing:
        widths = [d.textlength(c, font=f) for c in t]
        total = sum(widths) + spacing * (len(t) - 1)
        x = cx - total / 2
        for c, w in zip(t, widths):
            b = d.textbbox((0, 0), c, font=f)
            d.text((x - b[0], cy - (b[3] - b[1]) / 2 - b[1]), c, font=f, fill=fill)
            x += w + spacing
    else:
        b = d.textbbox((0, 0), t, font=f)
        d.text((cx - (b[0] + b[2]) / 2, cy - (b[1] + b[3]) / 2), t, font=f, fill=fill)


def draw_vtext(d, t, f, cx, top, fill, gap=6):
    y = top
    for c in t:
        b = d.textbbox((0, 0), c, font=f)
        d.text((cx - (b[0] + b[2]) / 2, y - b[1]), c, font=f, fill=fill)
        y += (b[3] - b[1]) + gap


# ------------------------------------------------------------------ 贴纸小图标
def deco(img, kind, cx, cy, s, ink=(178, 32, 48), soft=(240, 180, 120)):
    """s = 图标高度（px）。都是矢量画的，不需要额外素材。"""
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    if kind == "apple":
        r = s * 0.36
        d.ellipse((cx - r, cy - r * 1.05, cx + r * 0.55, cy + r * 0.95), fill=ink)
        d.ellipse((cx - r * 0.5, cy - r * 1.02, cx + r, cy + r * 0.9), fill=ink)
        d.line((cx, cy - r * 1.05, cx + s * 0.05, cy - s * 0.55), fill=(92, 70, 40), width=max(3, int(s * 0.03)))
        d.ellipse((cx + s * 0.02, cy - s * 0.62, cx + s * 0.22, cy - s * 0.5), fill=(96, 132, 74))
    elif kind == "star":
        import math
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rr = s * 0.5 if i % 2 == 0 else s * 0.21
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        d.polygon(pts, fill=soft)
    elif kind == "coin":
        r = s * 0.42
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(246, 212, 150), outline=(214, 160, 88), width=max(2, int(s * 0.03)))
        d.ellipse((cx - r * 0.45, cy - r * 0.45, cx + r * 0.45, cy + r * 0.45), outline=(214, 160, 88), width=max(2, int(s * 0.02)))
    elif kind == "flower":
        import math
        r = s * 0.22
        for i in range(5):
            a = i * 2 * math.pi / 5
            d.ellipse((cx + math.cos(a) * r * 1.1 - r, cy + math.sin(a) * r * 1.1 - r,
                       cx + math.cos(a) * r * 1.1 + r, cy + math.sin(a) * r * 1.1 + r), fill=(250, 226, 234))
        d.ellipse((cx - r * 0.4, cy - r * 0.4, cx + r * 0.4, cy + r * 0.4), fill=(246, 200, 90))
    elif kind == "sparkle":
        d.line((cx - s * 0.3, cy, cx + s * 0.3, cy), fill=soft, width=max(3, int(s * 0.05)))
        d.line((cx, cy - s * 0.3, cx, cy + s * 0.3), fill=soft, width=max(3, int(s * 0.05)))
    elif kind == "bear":
        r = s * 0.3
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(250, 236, 226))
        d.ellipse((cx - r * 1.25, cy - r * 1.15, cx - r * 0.45, cy - r * 0.35), fill=(250, 236, 226))
        d.ellipse((cx + r * 0.45, cy - r * 1.15, cx + r * 1.25, cy - r * 0.35), fill=(250, 236, 226))
        d.ellipse((cx - r * 0.5, cy - r * 0.15, cx - r * 0.2, cy + r * 0.15), fill=(120, 96, 84))
        d.ellipse((cx + r * 0.2, cy - r * 0.15, cx + r * 0.5, cy + r * 0.15), fill=(120, 96, 84))
        d.ellipse((cx - r * 0.12, cy + r * 0.2, cx + r * 0.12, cy + r * 0.34), fill=(120, 96, 84))
    elif kind == "bow":
        d.arc((cx - s, cy - s * 0.5, cx, cy + s * 0.5), 300, 240, fill=ink, width=max(3, int(s * 0.06)))
        d.arc((cx, cy - s * 0.5, cx + s, cy + s * 0.5), 300, 240, fill=ink, width=max(3, int(s * 0.06)))
    img.alpha_composite(lay) if img.mode == "RGBA" else img.paste(Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB"), (0, 0))


def soft_shadow(lay, blur=18, alpha=90, dy=12):
    a = lay.split()[-1].point(lambda v: int(v * alpha / 255))
    sh = Image.new("RGBA", lay.size, (0, 0, 0, 0))
    sh.paste((60, 30, 30, 255), (0, 0), a)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    off = Image.new("RGBA", lay.size, (0, 0, 0, 0))
    off.paste(sh, (0, dy))
    return off


def blob(size, color, r=0.44, seed=0):
    """手绘感云朵块：内层圆角矩形 + 上下边一排圆，拼出扇贝边。"""
    w, h = size
    lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    rr = int(min(w, h) * 0.17)
    d.rounded_rectangle((rr, rr, w - rr, h - rr), int(min(w, h) * 0.24), fill=color)
    n = max(3, int(w / (rr * 1.5)))
    for i in range(n + 1):
        x = rr + (w - 2 * rr) * i / n
        for y in (rr, h - rr):
            d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=color)
    for j in range(1, 3):
        y = h * j / 3
        for x in (rr, w - rr):
            d.ellipse((x - rr * 0.9, y - rr * 0.9, x + rr * 0.9, y + rr * 0.9), fill=color)
    return lay


def card(base: Image.Image, pg):
    W, H = base.size
    c = pg.get("card", {})
    img = base.convert("RGB")
    ink = tuple(c.get("ink", (168, 28, 44)))
    sub_ink = tuple(c.get("sub_ink", ink))
    title_f = F(c.get("title_font", "kuaile"), int(c.get("title_size", 210) * W / 1440))
    lines = c.get("title", pg.get("name", "")).split("\n")
    cy = c.get("title_cy", 0.47) * H
    lh = title_f.size * 1.22
    total = lh * len(lines)
    # 贴纸底块
    if c.get("blob", True):
        pad_x, pad_y = int(W * 0.09), int(W * 0.09)
        bw = max(int(max(ImageDraw.Draw(img).textlength(t, font=title_f) for t in lines) + pad_x * 2), int(W * 0.62))
        bh = int(total + pad_y * 1.6)
        bl = blob((bw, bh), ink + (255,) if len(ink) == 3 else ink)
        sh = soft_shadow(bl, blur=22, alpha=110, dy=16)
        x, y = int(W / 2 - bw / 2), int(cy - total / 2 - pad_y * 0.7)
        canvas = img.convert("RGBA")
        canvas.alpha_composite(sh, (x, y))
        canvas.alpha_composite(bl, (x, y))
        img = canvas.convert("RGB")
    d = ImageDraw.Draw(img)
    ty = cy - total / 2 + lh / 2
    tcol = tuple(c.get("title_ink", (255, 255, 255) if c.get("blob", True) else ink))
    for line in lines:
        draw_center(d, line, title_f, W / 2, ty, tcol, spacing=title_f.size * 0.04)
        ty += lh
    if c.get("sub"):
        f2 = F(c.get("sub_font", "kuaile"), int(c.get("sub_size", 62) * W / 1440))
        draw_center(d, c["sub"], f2, W / 2, cy + total / 2 + f2.size * 0.95, tcol)
    if c.get("eyebrow"):
        f3 = F("mashan", int(c.get("eyebrow_size", 76) * W / 1440))
        draw_center(d, c["eyebrow"], f3, W / 2, c.get("eyebrow_cy", 0.22) * H, sub_ink)
    if c.get("side"):
        f4 = F(c.get("side_font", "mashan"), int(c.get("side_size", 84) * W / 1440))
        sx = W * (0.87 if c.get("side_pos", "right") == "right" else 0.13)
        draw_vtext(d, c["side"], f4, sx, c.get("side_top", 0.1) * H, sub_ink)
        if c.get("seal"):
            fs = F("mashan", int(f4.size * 0.55))
            bx, by = sx - fs.size * 0.75, c.get("side_top", 0.1) * H + f4.size * (len(c["side"]) + 0.5)
            d.rounded_rectangle((bx, by, bx + fs.size * 1.5, by + fs.size * 1.5), int(fs.size * 0.2), fill=ink)
            draw_center(d, c["seal"], fs, bx + fs.size * 0.75, by + fs.size * 0.75, (255, 245, 240))
    if c.get("badge"):
        fb = F("kuaile", int(c.get("badge_size", 74) * W / 1440))
        tw = d.textlength(c["badge"], font=fb)
        bx, by = W / 2 - tw / 2 - fb.size * 0.7, H * c.get("badge_cy", 0.94)
        d.rounded_rectangle((bx, by - fb.size * 0.35, bx + tw + fb.size * 1.4, by + fb.size * 1.15),
                            int(fb.size * 0.75), fill=ink)
        draw_center(d, c["badge"], fb, W / 2, by + fb.size * 0.4, tuple(c.get("badge_ink", (255, 248, 240))))
    for i, kind in enumerate(c.get("deco", [])):
        s = int(c.get("deco_size", 150) * W / 1440)
        # spec.deco_pos 可给固定坐标；否则按环状均分摆放
        pos = c.get("deco_pos", [])
        if i < len(pos):
            cx, cyy = pos[i][0] * W, pos[i][1] * H
        else:
            import math
            a = -0.6 + i * 1.15
            cx = W / 2 + math.cos(a) * W * 0.36
            cyy = cy + math.sin(a) * H * 0.16
        deco(img, kind, cx, cyy, s, ink=ink, soft=tuple(c.get("soft", (243, 196, 120))))
    return img


def page_name(spec, pg):
    return f"{spec.get('prefix', '卡片')}{pg['n']:02d}-{pg.get('name', '')}"


def save(im, path, fmt):
    path = Path(path)
    im.convert("RGB").save(path, "PNG" if fmt == "png" else "JPEG", **({"compress_level": 6} if fmt == "png" else {"quality": 94, "subsampling": 0}))


def cmd_build(a, spec):
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    size = tuple(spec.get("canvas", [1326, 2880]))
    for pg in spec["pages"]:
        src = Path(a.art_dir) / f"{pg['n']:02d}.png"
        if not src.exists():
            print(f"[skip] {src} 不存在"); continue
        base = Image.open(src).convert("RGB").resize(size, Image.LANCZOS)
        im = card(base, pg)
        save(im, out / f"{page_name(spec, pg)}.{a.format}", a.format)
        print(f"[card] {page_name(spec, pg)} {im.size}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("spec"); b.add_argument("--art-dir", required=True); b.add_argument("--out", required=True); b.add_argument("--format", default="png", choices=["png", "jpg"])
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    if a.cmd == "build":
        cmd_build(a, spec)


if __name__ == "__main__":
    main()
