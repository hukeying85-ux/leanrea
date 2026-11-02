#!/usr/bin/env python3
"""healing-comic 排版器 v3：复刻模式（xhs）+ 海报模式（poster）。

xhs 模式按对参考帖《毁掉关系的八种做法》8 张原图的逐像素测量复刻：
- 画布 1080×1440（原图 1080×1447，差 7px 忽略）
- 整页满版插画，画到四边（底部无白边）；顶部 ~12% 干净暖纸条放标题
- 封面：主标题 76px Medium 居中两行 + 钩子句 34px（原帖封面为 63px 居中 + 大字区）
- 内容页：标题 54px Medium 居中一行 + 副题 30px（原帖 57-66px 居中）
- 气泡：白色、深棕黑 4px 描边，置于画面中部（原帖对白均画在场景内）
- 无页眉小标签、无页码、无页脚（原帖均无；署名放正文配文）
- 色板取自原图：纸 #F5F1E8 / 蜜桃 #F0D1C0 / 棕 #A48476 / 墨 #301412

poster 模式 = v2（taste-skill 审校版），供竖版知识卡使用。

用法:
  python3 compose.py spec.json --layout xhs --font r.ttf --font-medium m.ttf \
      --art-root examples --outdir examples/pages-xhs --html --contact-sheet
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    sys.exit("需要 Pillow：python3 -m pip install Pillow")

W, H = 1080, 1440
MARGIN = 72
CREAM = "#F5F1E8"                # 实测暖纸底
INK = "#301412"                  # 实测墨色（近黑深棕）
MUTED = "#7A6A63"
BUBBLE = "#FFFFFF"
CLOSERS = "，。！？、；：）」』】…～,.!?;:)]}"
MAXW = W - 2 * MARGIN


def load(env: str, explicit: str | None, fallback: str | None = None) -> str:
    for p in [explicit or "", os.environ.get(env, ""), fallback or ""]:
        if p and Path(os.path.expanduser(p)).is_file():
            return os.path.expanduser(p)
    return ""


def wrap(text: str, font, draw, max_width: int) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if cur and draw.textlength(trial, font=font) > max_width:
            if ch in CLOSERS:
                cur = trial
            else:
                lines.append(cur)
                cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_bubble(draw, lines, font, y_top: int = 470) -> None:
    """复刻原帖气泡：白底 + 深墨 4px 描边，画面中部，尾巴指向下方角色。"""
    pad_x, pad_y, lh = 52, 38, 68
    x0, x1 = 90, W - 90
    body_h = pad_y * 2 + lh * len(lines)
    y0, y1 = y_top, y_top + body_h

    tx = x0 + 110
    draw.polygon([(tx, y0 + 12), (tx + 34, y0 - 46), (tx + 116, y0 + 12)],
                 fill=BUBBLE, outline=INK, width=4)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=34,
                           fill=BUBBLE, outline=INK, width=4)
    for i, line in enumerate(lines):
        draw.text((x0 + pad_x, y0 + pad_y + i * lh), line,
                  font=font, fill=INK)


def render(item: dict, art_root: Path, outdir: Path, fonts: dict,
           index: int, layout: str) -> Path:
    art = art_root / item["art"]
    if not art.is_file():
        sys.exit(f"缺少底图：{art}")
    im = ImageOps.fit(Image.open(art).convert("RGB"), (W, H),
                      method=Image.LANCZOS, centering=(0.5, 0.5))
    draw = ImageDraw.Draw(im)
    mode = item.get("layout", layout)

    title = item.get("title", "")
    if isinstance(title, list):
        title_lines = list(title)
    else:
        title_lines = [title]
    subtitle = item.get("subtitle", "")

    problems: list[str] = []

    if mode == "xhs-cover":
        # 封面：76px Medium 居中（可两行）+ 34px 钩子句，全部落在顶部纸条
        y = 64
        for i, line in enumerate(title_lines[:2]):
            draw.text(((W - draw.textlength(line, font=fonts['cover'])) / 2,
                       y + i * 100), line, font=fonts['cover'], fill=INK,
                      stroke_width=3, stroke_fill=CREAM)
        y = 64 + len(title_lines[:2]) * 100 + 26
        if subtitle:
            draw.text(((W - draw.textlength(subtitle, font=fonts['hook'])) / 2, y),
                      subtitle, font=fonts['hook'], fill=MUTED,
                      stroke_width=2, stroke_fill=CREAM)
        if len(title_lines) > 2:
            problems.append("封面标题超过两行")
        for line in title_lines[:2]:
            if draw.textlength(line, font=fonts['cover']) > W - 120:
                problems.append(f"封面标题行超宽：{line}")
    elif mode == "xhs":
        # 内容页：54px Medium 居中一行 + 30px 副题
        draw.text(((W - draw.textlength(title_lines[0], font=fonts['xhs_title'])) / 2, 84),
                  title_lines[0], font=fonts['xhs_title'], fill=INK,
                  stroke_width=3, stroke_fill=CREAM)
        if subtitle:
            draw.text(((W - draw.textlength(subtitle, font=fonts['xhs_sub'])) / 2, 172),
                      subtitle, font=fonts['xhs_sub'], fill=MUTED,
                      stroke_width=2, stroke_fill=CREAM)
        if len(title_lines) > 1:
            problems.append(f"内容页标题应一行：{title_lines}")
        if draw.textlength(title_lines[0], font=fonts['xhs_title']) > W - 110:
            problems.append(f"标题超宽：{title_lines[0]}")
    else:  # poster（v2）
        draw.text((MARGIN, 104), title_lines[0], font=fonts['p_title'],
                  fill=INK, stroke_width=3, stroke_fill=CREAM)
        ty = 104 + (draw.textbbox((MARGIN, 104), title_lines[0],
                                  font=fonts['p_title'])[3] if title_lines[0] else 0)
        if subtitle:
            draw.text((MARGIN, ty + 34), subtitle, font=fonts['p_sub'],
                      fill=MUTED, stroke_width=2, stroke_fill=CREAM)
        footer = item.get("footer", "")
        if item.get("kicker"):
            footer = f"{item['kicker']} · {footer}" if footer else item["kicker"]
        draw.text((MARGIN, 1364), footer, font=fonts['p_footer'],
                  fill=MUTED, stroke_width=2, stroke_fill=CREAM)
        if draw.textlength(title_lines[0], font=fonts['p_title']) > MAXW:
            problems.append(f"标题超宽：{title_lines[0]}")

    # 气泡（xhs / poster 共用；poster 在底部，xhs 在中部）
    if item.get("bubble"):
        bubble_lines: list[str] = []
        bf = fonts['bubble']
        for part in item["bubble"]:
            bubble_lines.extend(wrap(part, bf, draw, W - 180 - 104))
        if mode.startswith("xhs"):
            draw_bubble(draw, bubble_lines, bf, y_top=486)
        else:
            draw_bubble(draw, bubble_lines, bf, y_top=1332 - 76 * len(bubble_lines))
        if len(bubble_lines) > 3:
            problems.append(f"气泡超过 3 行（{len(bubble_lines)}）")

    if problems:
        sys.exit(f"[gate FAIL] 第 {index} 页：\n  - " + "\n  - ".join(problems))

    out = outdir / item.get("out", f"{index:02d}.png")
    im.save(out, "PNG")
    return out


def write_html(outdir: Path, files: list[Path], items: list[dict],
               heading: str, subheading: str) -> Path:
    cards = []
    for p, it in zip(files, items):
        t = it.get("title")
        cap = " ".join(t) if isinstance(t, list) else (t or "")
        sub = it.get("subtitle", "")
        line = " ".join(it.get("bubble", []))
        cards.append(
            f'<figure><img src="{html.escape(p.name)}" alt="{html.escape(cap)}">'
            f"<figcaption><b>{html.escape(cap)}</b>"
            f"{'<br>' + html.escape(sub) if sub else ''}"
            f"<br>{html.escape(line)}</figcaption></figure>"
        )
    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(heading)}</title>
<style>
body{{margin:0;background:#EFE9DD;color:#301412;
 font-family:"LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif}}
header{{padding:48px 24px 4px;max-width:1200px;margin:0 auto}}
h1{{font-size:34px;margin:0 0 10px;font-weight:600}}
header p{{margin:4px 0;color:#7A6A63;font-size:15px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
 gap:20px;max-width:1200px;margin:20px auto 64px;padding:0 24px}}
figure{{margin:0;background:#FFFDF8;border:1px solid #E2D8C6}}
img{{width:100%;display:block}}
figcaption{{padding:13px 16px 17px;font-size:15px;line-height:1.7}}
</style></head><body>
<header><h1>{html.escape(heading)}</h1><p>{html.escape(subheading)}</p></header>
<div class="grid">{''.join(cards)}</div>
</body></html>"""
    p = outdir / "preview.html"
    p.write_text(doc, encoding="utf-8")
    (outdir / "index.html").write_text(doc, encoding="utf-8")
    return p


def write_contact_sheet(outdir: Path, files: list[Path]) -> Path:
    tw, th = 300, 400
    cols = min(3, len(files))
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (tw * cols, th * rows), "#FFFFFF")
    d = ImageDraw.Draw(sheet)
    for i, p in enumerate(files):
        im = ImageOps.fit(Image.open(p).convert("RGB"), (tw, th - 24),
                          method=Image.LANCZOS)
        x, y = (i % cols) * tw, (i // cols) * th
        sheet.paste(im, (x, y))
    out = outdir / "preview.jpg"
    sheet.save(out, "JPEG", quality=90)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--font")
    ap.add_argument("--font-medium")
    ap.add_argument("--art-root", type=Path, default=None)
    ap.add_argument("--outdir", type=Path, default=None)
    ap.add_argument("--layout", choices=["xhs", "poster"], default="xhs",
                    help="spec 未逐页指定 layout 时使用的默认模式")
    ap.add_argument("--html", action="store_true")
    ap.add_argument("--contact-sheet", action="store_true")
    ap.add_argument("--heading", default="引导型恋人，从不做的 8 件事")
    ap.add_argument("--subheading", default="复刻《毁掉关系的八种做法》版式 · 1080×1440")
    a = ap.parse_args()

    spec = a.spec.resolve()
    items = json.loads(spec.read_text(encoding="utf-8"))
    art_root = (a.art_root or spec.parent).resolve()
    outdir = (a.outdir or spec.parent / "pages").resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    reg = load("COMIC_FONT", a.font)
    med = load("COMIC_FONT_MEDIUM", a.font_medium, reg)
    if not reg:
        sys.exit("找不到中文字体：--font 指定 .ttf/.ttc，或设 COMIC_FONT")

    fonts = {
        'cover': ImageFont.truetype(med, 76),
        'hook': ImageFont.truetype(reg, 34),
        'xhs_title': ImageFont.truetype(med, 54),
        'xhs_sub': ImageFont.truetype(reg, 30),
        'p_title': ImageFont.truetype(med, 80),
        'p_sub': ImageFont.truetype(reg, 42),
        'p_footer': ImageFont.truetype(reg, 26),
        'bubble': ImageFont.truetype(med, 44),
    }

    files = [render(it, art_root, outdir, fonts, i, a.layout)
             for i, it in enumerate(items, 1)]
    print(f"[compose] {len(files)} pages -> {outdir}  [gate] all pass")
    if a.html:
        print(f"[compose] {write_html(outdir, files, items, a.heading, a.subheading)}")
    if a.contact_sheet:
        print(f"[compose] {write_contact_sheet(outdir, files)}")


if __name__ == "__main__":
    main()
