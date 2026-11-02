#!/usr/bin/env python3
"""healing-comic 排版器 v4：复刻模式两代（xhs / xhs2）+ 海报模式（poster）。

xhs2 模式 = 复刻 2.0，依据 ocr_layout.py 对 8 张原图的 OCR + 逐像素测量
（references/layout-xhs8.json）：
- 画布 1080×1447（与原图完全一致）
- 结构：两段式 —— 顶部标签(66px Medium 居中, cy≈0.073) → 上半场场景+气泡
  → 中幅点题句(56px Medium 居中, cy≈0.568) → 下半场场景+气泡
- 气泡：白底 + 墨色 3px 描边的微扰椭圆（手绘云朵感），锚点取自原帖
  对白文字框中心的实测比例坐标，字号 34px 行距 44px
- 墨色实测 #32150D 附近，纸纹由底图自带（底图 = 原帖去字编辑图）

xhs 模式 = 复刻 1.0（单场景 + 顶部标题/副题 + 中部气泡带），保留作对照。
poster 模式 = v2（taste-skill 审校版），供竖版知识卡使用。

用法:
  python3 compose.py spec.json --layout xhs2 --font r.ttf --font-medium m.ttf \
      --art-root examples --outdir examples/pages-xhs2 --html --contact-sheet
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    sys.exit("需要 Pillow：python3 -m pip install Pillow")

W, H = 1080, 1440            # xhs v1 / poster 画布
XHS2 = (1080, 1447)          # xhs2 画布 = 原图尺寸
MARGIN = 72
CREAM = "#F5F1E8"            # 实测暖纸底
INK = "#301412"              # 实测墨色（近黑深棕）
MUTED = "#7A6A63"
BUBBLE = "#FFFFFF"
CLOSERS = "，。！？、；：）」』】…～,.!?;:)]}"
MAXW = W - 2 * MARGIN

# xhs2 版式常量（references/layout-xhs8.json 实测均值）
LABEL_CY = 0.073             # 标签中心 y（0.063–0.095）
REVEAL_CY = 0.568            # 点题句中心 y（0.560–0.606）


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
    """xhs v1 气泡：白底 + 深墨 4px 描边圆角矩形，画面中部。"""
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


def _wobble_ellipse(cx: float, cy: float, rx: float, ry: float, seed: int):
    """微扰椭圆：模拟原帖手绘云朵气泡（实测形状充实率 0.5–0.68）。"""
    pts = []
    n = 36
    for i in range(n):
        th = 2 * math.pi * i / n
        w = 1 + 0.035 * math.sin(th * 3 + seed) + 0.018 * math.sin(th * 5 + seed * 2)
        pts.append((cx + rx * w * math.cos(th), cy + ry * w * math.sin(th)))
    return pts


def draw_bubble2(draw, lines, font, anchor, canvas, seed: int = 3) -> None:
    """xhs2 气泡：白底 + 墨色 3px 描边微扰椭圆；anchor=文字中心（比例坐标）。"""
    cx = anchor[0] * canvas[0]
    cy = anchor[1] * canvas[1]
    lh = 44
    wid = max((draw.textlength(t, font=font) for t in lines), default=0)
    rx = wid / 2 + 28
    ry = len(lines) * lh / 2 + 22
    pts = _wobble_ellipse(cx, cy, rx, ry, seed)
    draw.polygon(pts, fill=BUBBLE)
    draw.line(pts + [pts[0]], fill=INK, width=3, joint="curve")
    for i, t in enumerate(lines):
        yc = cy - len(lines) * lh / 2 + (i + 0.5) * lh
        draw.text((cx, yc), t, font=font, fill=INK, anchor="mm")


def render(item: dict, art_root: Path, outdir: Path, fonts: dict,
           index: int, layout: str) -> Path:
    art = art_root / item["art"]
    if not art.is_file():
        sys.exit(f"缺少底图：{art}")
    mode = item.get("layout", layout)
    canvas = XHS2 if mode.startswith("xhs2") else (W, H)
    im = ImageOps.fit(Image.open(art).convert("RGB"), canvas,
                      method=Image.LANCZOS, centering=(0.5, 0.5))
    draw = ImageDraw.Draw(im)

    title = item.get("title", "")
    if isinstance(title, list):
        title_lines = list(title)
    else:
        title_lines = [title]
    subtitle = item.get("subtitle", "")

    problems: list[str] = []

    if mode in ("xhs-cover", "xhs2-cover"):
        # 封面：76px Medium 居中（可两行）+ 34px 钩子句，全部落在顶部纸条
        y = 64
        for i, line in enumerate(title_lines[:2]):
            draw.text(((canvas[0] - draw.textlength(line, font=fonts['cover'])) / 2,
                       y + i * 100), line, font=fonts['cover'], fill=INK,
                      stroke_width=3, stroke_fill=CREAM)
        y = 64 + len(title_lines[:2]) * 100 + 26
        if subtitle:
            draw.text(((canvas[0] - draw.textlength(subtitle, font=fonts['hook'])) / 2, y),
                      subtitle, font=fonts['hook'], fill=MUTED,
                      stroke_width=2, stroke_fill=CREAM)
        if len(title_lines) > 2:
            problems.append("封面标题超过两行")
        for line in title_lines[:2]:
            if draw.textlength(line, font=fonts['cover']) > canvas[0] - 120:
                problems.append(f"封面标题行超宽：{line}")
    elif mode == "xhs2":
        # 两段式复刻：标签 → 上半场气泡 → 点题句 → 下半场气泡（锚点=原帖实测）
        label = item.get("label", "")
        draw.text((canvas[0] / 2, LABEL_CY * canvas[1]), label,
                  font=fonts['label'], fill=INK, anchor="mm",
                  stroke_width=2, stroke_fill=CREAM)
        if item.get("reveal"):
            draw.text((canvas[0] / 2, REVEAL_CY * canvas[1]), item["reveal"],
                      font=fonts['reveal'], fill=INK, anchor="mm",
                      stroke_width=2, stroke_fill=CREAM)
        for bi, b in enumerate(item.get("bubbles", [])):
            draw_bubble2(draw, b["lines"], fonts['bub'], b["anchor"], canvas,
                         seed=index * 10 + bi * 3 + 3)
        # gate
        if draw.textlength(label, font=fonts['label']) > canvas[0] - 120:
            problems.append(f"标签超宽：{label}")
        if item.get("reveal") and \
                draw.textlength(item["reveal"], font=fonts['reveal']) > canvas[0] - 120:
            problems.append(f"点题句超宽：{item['reveal']}")
        for b in item.get("bubbles", []):
            wpx = max(draw.textlength(t, font=fonts['bub']) for t in b["lines"]) + 56
            if wpx > 470:
                problems.append(f"气泡过宽（{int(wpx)}px）：{b['lines']}")
            if len(b["lines"]) > 3:
                problems.append(f"气泡超过 3 行：{b['lines']}")
            cx = b["anchor"][0] * canvas[0]
            if cx - wpx / 2 < 8 or cx + wpx / 2 > canvas[0] - 8:
                problems.append(f"气泡出界：{b['lines']}")
    elif mode == "xhs":
        # v1 内容页：54px Medium 居中一行 + 30px 副题
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

    # v1/poster 气泡（xhs2 在自己的分支里画）
    if item.get("bubble") and not mode.startswith("xhs2"):
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
        if it.get("label"):
            cap = it.get("label", "")
            sub = it.get("reveal", "")
            line = " / ".join(" ".join(b["lines"]) for b in it.get("bubbles", []))
        else:
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
    ap.add_argument("--layout", choices=["xhs", "xhs2", "poster"], default="xhs2",
                    help="spec 未逐页指定 layout 时使用的默认模式")
    ap.add_argument("--html", action="store_true")
    ap.add_argument("--contact-sheet", action="store_true")
    ap.add_argument("--heading", default="引导型恋人，从不做的 8 件事")
    ap.add_argument("--subheading", default="复刻《毁掉关系的八种做法》版式 · 1080×1447")
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
        'label': ImageFont.truetype(med, 66),
        'reveal': ImageFont.truetype(med, 56),
        'bub': ImageFont.truetype(med, 34),
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
