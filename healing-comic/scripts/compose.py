#!/usr/bin/env python3
"""healing-comic 排版器 v2（taste-skill 审校版）：无字底图 + spec.json -> 1080x1440 成品页。

本版按 Leonxlnx/taste-skill 的 house rules 重排：
- 删页眉小标签（eyebrow/pill 一律禁止）——出处信息并入页脚
- 删右上角页码（index numbering 禁止；轮播位置由平台显示）
- 「一个超大 + 一个小」做视觉工作：大标题 80px Medium；支持句 42px；
  台词是 statement（气泡内左对齐 46px）；页脚 26px
- 全部左对齐，共享同一条左边线（72px 网格）
- 无渐变、无阴影、无细线装饰；文字奶油描边光环 = 唯一允许的「图上文字中性纱」
- --gate：渲染后实测字宽/行数，超限直接报错（inspect 的本地等价物）

只依赖 Pillow，不联网、不调模型、不覆盖 art/ 原图。

用法:
  python3 compose.py spec.json --font regular.ttf --font-medium medium.ttf \
      --art-root examples --outdir examples/pages --html --contact-sheet
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
MARGIN = 72                      # 唯一外边距，左右共享同一条左边线
CREAM = "#FFF8EE"
INK = "#4A3B32"
MUTED = "#9A8B7E"
BUBBLE = "#FFFFFF"
CLOSERS = "，。！？、；：）」』】…～,.!?;:)]}"

MAXW = W - 2 * MARGIN            # 936：标题/支持句/页脚的统一measure


def load(env: str, explicit: str | None, fallback: str | None = None) -> str:
    for p in [explicit or "", os.environ.get(env, ""), fallback or ""]:
        if p and Path(os.path.expanduser(p)).is_file():
            return os.path.expanduser(p)
    return ""


def wrap(text: str, font, draw, max_width: int) -> list[str]:
    """中文按字折行；行首不出现收尾标点。"""
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


def draw_bubble(draw, lines, font) -> None:
    """白色对话气泡：comic 媒介自身的语义元素（非 UI 分隔线），
    ink 描边、文字左对齐、尾巴指向下方角色。"""
    pad_x, pad_y, lh = 46, 36, 66
    x0, x1 = MARGIN, W - MARGIN
    y1 = 1332
    body_h = pad_y * 2 + lh * len(lines)
    y0 = y1 - body_h

    # 尾巴：先画，气泡矩形盖住其上缘，只露出指向角色的尖端
    tx = x0 + 96
    draw.polygon([(tx, y0 + 10), (tx + 30, y0 - 42), (tx + 104, y0 + 10)],
                 fill=BUBBLE, outline=INK, width=4)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=36,
                           fill=BUBBLE, outline=INK, width=4)
    for i, line in enumerate(lines):
        draw.text((x0 + pad_x, y0 + pad_y + i * lh), line,
                  font=font, fill=INK)


def render(item: dict, art_root: Path, outdir: Path,
           f_title, f_sub, f_bubble, f_footer, index: int) -> Path:
    art = art_root / item["art"]
    if not art.is_file():
        sys.exit(f"缺少底图：{art}")
    im = ImageOps.fit(Image.open(art).convert("RGB"), (W, H),
                      method=Image.LANCZOS, centering=(0.5, 0.5))
    draw = ImageDraw.Draw(im)

    title = item.get("title", "")
    if isinstance(title, list):
        title = title[0] if title else ""
    subtitle = item.get("subtitle", "")

    # --- 大标题：一行超大，taste: display leading 0.85–1.05 ---
    y = 104
    draw.text((MARGIN, y), title, font=f_title, fill=INK,
              stroke_width=3, stroke_fill=CREAM)          # 唯一允许的图上文字纱
    ty = y + (draw.textbbox((MARGIN, y), title, font=f_title)[3]
              if title else 0)

    # --- 支持句：直接在大标题下方（taste: one supporting sentence）---
    if subtitle:
        draw.text((MARGIN, ty + 34), subtitle, font=f_sub, fill=MUTED,
                  stroke_width=2, stroke_fill=CREAM)

    # --- 台词气泡 ---
    bubble_lines: list[str] = []
    for part in item.get("bubble", []):
        bubble_lines.extend(wrap(part, f_bubble, draw,
                                 W - 2 * MARGIN - 92))
    draw_bubble(draw, bubble_lines, f_bubble)

    # --- 页脚：designed close，含出处（旧版 kicker 并入此处）---
    footer = item.get("footer", "")
    if item.get("kicker"):                                  # 向后兼容 v1 spec
        footer = f"{item['kicker']} · {footer}" if footer else item["kicker"]
    draw.text((MARGIN, 1364), footer, font=f_footer, fill=MUTED,
              stroke_width=2, stroke_fill=CREAM)

    # --- gate：taste inspect 的本地等价物，超限即 FAIL ---
    problems = []
    if draw.textlength(title, font=f_title) > MAXW:
        problems.append(f"标题超宽 {int(draw.textlength(title, font=f_title))}px > {MAXW}px：{title}")
    if draw.textlength(subtitle, font=f_sub) > MAXW:
        problems.append(f"支持句超宽：{subtitle}")
    if draw.textlength(footer, font=f_footer) > MAXW:
        problems.append(f"页脚超宽：{footer}")
    if len(bubble_lines) > 3:
        problems.append(f"气泡超过 3 行（{len(bubble_lines)} 行）")
    if problems:
        sys.exit(f"[gate FAIL] 第 {index} 页：\n  - " + "\n  - ".join(problems))

    out = outdir / item.get("out", f"{index:02d}.png")
    im.save(out, "PNG")
    return out


def write_html(outdir: Path, files: list[Path], items: list[dict],
               heading: str, subheading: str) -> Path:
    cards = []
    for i, (p, it) in enumerate(zip(files, items), 1):
        cap = it.get("title", "")
        sub = it.get("subtitle", "")
        line = " ".join(it.get("bubble", []))
        foot = it.get("footer", "")
        cards.append(
            f'<figure><img src="{html.escape(p.name)}" alt="{html.escape(cap)}">'
            f"<figcaption><b>{html.escape(cap)}</b>"
            f"{'<br>' + html.escape(sub) if sub else ''}"
            f"<br>{html.escape(line)}<br><small>{html.escape(foot)}</small>"
            f"</figcaption></figure>"
        )
    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(heading)}</title>
<style>
body{{margin:0;background:#F3EDE3;color:#4A3B32;
 font-family:"LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif}}
header{{padding:56px 24px 8px;text-align:left;max-width:1200px;margin:0 auto}}
h1{{font-size:34px;margin:0 0 10px;font-weight:600}}
header p{{margin:4px 0;color:#9A8B7E;font-size:15px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
 gap:24px;max-width:1200px;margin:24px auto 64px;padding:0 24px}}
figure{{margin:0;background:#FFFDF8;border:1px solid #E5DCCB}}
img{{width:100%;display:block}}
figcaption{{padding:14px 16px 18px;font-size:15px;line-height:1.7;text-align:left}}
figcaption small{{color:#9A8B7E}}
</style></head><body>
<header><h1>{html.escape(heading)}</h1>
<p>{html.escape(subheading)}</p></header>
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
        im = ImageOps.fit(Image.open(p).convert("RGB"), (tw, th - 26),
                          method=Image.LANCZOS)
        x, y = (i % cols) * tw, (i // cols) * th
        sheet.paste(im, (x, y))
        d.text((x + 8, y + th - 22), p.name, fill=INK)
    out = outdir / "preview.jpg"
    sheet.save(out, "JPEG", quality=90)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--font", help="中文 Regular .ttf/.ttc")
    ap.add_argument("--font-medium", help="中文 Medium/Bold .ttf（标题与台词）")
    ap.add_argument("--art-root", type=Path, default=None)
    ap.add_argument("--outdir", type=Path, default=None)
    ap.add_argument("--html", action="store_true")
    ap.add_argument("--contact-sheet", action="store_true")
    ap.add_argument("--heading", default="把选择权还回去，再在旁边站得稳一点")
    ap.add_argument("--subheading",
                    default="《引导型恋人指南 v1.1.0》四条底线 · 1080×1440 · "
                            "画风参考「一二布布」（黄小B）· 中文由脚本合成")
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

    f_title = ImageFont.truetype(med, 80)
    f_sub = ImageFont.truetype(reg, 42)
    f_bubble = ImageFont.truetype(med, 46)
    f_footer = ImageFont.truetype(reg, 26)

    files = [render(it, art_root, outdir, f_title, f_sub, f_bubble, f_footer, i)
             for i, it in enumerate(items, 1)]
    print(f"[compose] {len(files)} pages -> {outdir}  [gate] all pass")
    if a.html:
        print(f"[compose] {write_html(outdir, files, items, a.heading, a.subheading)}")
    if a.contact_sheet:
        print(f"[compose] {write_contact_sheet(outdir, files)}")


if __name__ == "__main__":
    main()
