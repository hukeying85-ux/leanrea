#!/usr/bin/env python3
"""healing-comic 排版器：无字底图 + spec.json -> 1080x1440 小红书漫画成品页。

只依赖 Pillow，不联网、不调模型、不覆盖 art/ 原图。
所有中文由这里绘制，生图模型永远不写字。

用法:
  python3 compose.py spec.json --font /path/to/CJK.ttf \
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
CREAM = "#FFF8EE"
INK = "#4A3B32"
MUTED = "#9A8B7E"
LINE = "#6B5748"
BUBBLE = "#FFFFFF"
ACCENT = "#E8B44A"
CLOSERS = "，。！？、；：）」』】…～,.!?;:)]}"

FONT_CANDIDATES = [
    os.environ.get("COMIC_FONT", ""),
    "~/.fonts/LXGWWenKai-Regular.ttf",
    "~/Library/Fonts/LXGWWenKai-Regular.ttf",
    "~/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]


def find_font(explicit: str | None) -> str:
    for p in [explicit or "", *FONT_CANDIDATES]:
        if p and Path(os.path.expanduser(p)).is_file():
            return os.path.expanduser(p)
    sys.exit(
        "找不到中文字体。请用 --font 指定一个 .ttf/.ttc，或设 COMIC_FONT。\n"
        "推荐霞鹜文楷（SIL OFL 1.1）：见 scripts/fetch_font.sh"
    )


def wrap(text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw,
         max_width: int) -> list[str]:
    """中文按字折行，行首不出现收尾标点。"""
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if cur and draw.textlength(trial, font=font) > max_width:
            if ch in CLOSERS:            # 标点跟着上一行，不落单到行首
                cur = trial
            else:
                lines.append(cur)
                cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_bubble(draw: ImageDraw.ImageDraw, lines: list[str],
                font: ImageFont.FreeTypeFont, bottom: int = 1348) -> None:
    pad_x, pad_y, lh = 46, 34, 66
    box_w = W - 152
    body_h = pad_y * 2 + lh * len(lines)
    x0, x1 = 76, 76 + box_w
    y1, y0 = bottom, bottom - body_h

    # 小尾巴（先画，气泡盖住底边，只露出尖端）
    tx = 250
    draw.polygon([(tx, y0 + 12), (tx + 26, y0 - 34), (tx + 96, y0 + 12)],
                 fill=BUBBLE, outline=LINE, width=5)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=42,
                           fill=BUBBLE, outline=LINE, width=5)

    for i, line in enumerate(lines):
        tw = draw.textlength(line, font=font)
        draw.text(((W - tw) / 2, y0 + pad_y + i * lh), line,
                  font=font, fill=INK)


def render(item: dict, art_root: Path, outdir: Path,
           font_path: str, index: int, total: int) -> Path:
    art = art_root / item["art"]
    if not art.is_file():
        sys.exit(f"缺少底图：{art}")
    im = ImageOps.fit(Image.open(art).convert("RGB"), (W, H),
                      method=Image.LANCZOS, centering=(0.5, 0.5))
    draw = ImageDraw.Draw(im)

    f_kicker = ImageFont.truetype(font_path, 30)
    f_title = ImageFont.truetype(font_path, 66)
    f_bubble = ImageFont.truetype(font_path, 46)
    f_footer = ImageFont.truetype(font_path, 24)

    # 左上小标签
    draw.text((76, 78), item.get("kicker", ""), font=f_kicker, fill=MUTED)
    # 右上页码
    badge = f"{index:02d} / {total:02d}"
    draw.text((W - 76 - draw.textlength(badge, font=f_kicker), 78),
              badge, font=f_kicker, fill=MUTED)

    # 大标题（最多两行）
    title = item.get("title", [])
    y = 140
    for i, line in enumerate(title[:2]):
        draw.text((76, y + i * 86), line, font=f_title, fill=INK)
    underline_y = y + len(title[:2]) * 86 + 6
    draw.line([(78, underline_y), (150, underline_y - 4),
               (232, underline_y + 3), (300, underline_y - 2)],
              fill=ACCENT, width=7, joint="curve")

    # 气泡：数组里的每一项是作者指定的一行，必要时再各自折行
    bubble_lines: list[str] = []
    for part in item.get("bubble", []):
        bubble_lines.extend(wrap(part, f_bubble, draw, W - 152 - 92))
    draw_bubble(draw, bubble_lines, f_bubble)

    # 页脚出处
    draw.text((76, H - 48), item.get("footer", ""), font=f_footer, fill=MUTED)

    out = outdir / item.get("out", f"{index:02d}.png")
    im.save(out, "PNG")
    return out


def write_html(outdir: Path, files: list[Path], items: list[dict]) -> Path:
    cards = []
    for i, (p, it) in enumerate(zip(files, items), 1):
        caption = " ".join(it.get("title", []))
        line = " ".join(it.get("bubble", []))
        cards.append(
            f'<figure><img src="{html.escape(p.name)}" alt="{html.escape(caption)}">'
            f'<figcaption><b>{i:02d} · {html.escape(caption)}</b><br>'
            f'{html.escape(line)}<br><small>{html.escape(it.get("footer", ""))}</small>'
            f"</figcaption></figure>"
        )
    doc = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>healing-comic 样张 · 引导型恋人指南 四条底线</title>
<style>
body{{margin:0;background:#F3EDE3;color:#4A3B32;
 font-family:"LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif}}
header{{padding:40px 24px 8px;text-align:center}}
h1{{font-size:30px;margin:0 0 8px}}
header p{{margin:4px 0;color:#9A8B7E;font-size:15px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
 gap:24px;max-width:1200px;margin:24px auto 60px;padding:0 24px}}
figure{{margin:0;background:#fff;border-radius:18px;overflow:hidden;
 box-shadow:0 6px 22px rgba(74,59,50,.10)}}
img{{width:100%;display:block}}
figcaption{{padding:14px 16px 18px;font-size:15px;line-height:1.7}}
figcaption small{{color:#9A8B7E}}
</style></head><body>
<header><h1>把选择权还回去，再在旁边站得稳一点</h1>
<p>《引导型恋人指南 v1.1.0》四条底线 · 6 页 · 1080×1440 · 画风参考「一二布布」（黄小B）</p>
<p>中文由 scripts/compose.py 后期合成，生图阶段零文字 · 一二布布为黄小B 的 IP：发布署名并勾选 AI 标识；商用换 examples/art-original/ 原创版</p></header>
<div class="grid">{''.join(cards)}</div>
</body></html>"""
    p = outdir / "preview.html"
    p.write_text(doc, encoding="utf-8")
    (outdir / "index.html").write_text(doc, encoding="utf-8")  # 静态服务器默认页
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
        d.text((x + 8, y + th - 22), p.name, fill="#4A3B32")
    out = outdir / "preview.jpg"
    sheet.save(out, "JPEG", quality=90)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec", type=Path, help="spec.json 路径")
    ap.add_argument("--font", help="中文 .ttf/.ttc 路径（也可用 COMIC_FONT）")
    ap.add_argument("--art-root", type=Path, default=None,
                    help="art/ 的根目录，默认 spec.json 所在目录")
    ap.add_argument("--outdir", type=Path, default=None,
                    help="输出目录，默认 spec 同级 pages/")
    ap.add_argument("--html", action="store_true", help="生成 index.html 预览")
    ap.add_argument("--contact-sheet", action="store_true", help="生成 preview.jpg")
    a = ap.parse_args()

    spec = a.spec.resolve()
    items = json.loads(spec.read_text(encoding="utf-8"))
    art_root = (a.art_root or spec.parent).resolve()
    outdir = (a.outdir or spec.parent / "pages").resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    font = find_font(a.font)

    files = [render(it, art_root, outdir, font, i, len(items))
             for i, it in enumerate(items, 1)]
    print(f"[compose] {len(files)} pages -> {outdir}")
    if a.html:
        print(f"[compose] {write_html(outdir, [p for p in files], items)}")
    if a.contact_sheet:
        print(f"[compose] {write_contact_sheet(outdir, files)}")


if __name__ == "__main__":
    main()
