#!/usr/bin/env python3
"""compare_sheet.py —— 把「无 UI 版」和「有 UI 版」并成一张总预览图。

用法:
  python3 scripts/compare_sheet.py SPEC.json --clean 无UI目录 --ui 有UI目录 \
          --out 总预览图.jpg [--format jpg|png]

上排 = 干净壁纸，下排 = 同画幅叠了 iOS 锁屏/主屏的预览；每格左上角标 无 UI / 锁屏 / 主屏。
只找两排都齐的页；缺图会在控制台报出来，补齐后重跑即可整张刷新。
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CJK = ["~/.fonts/LXGWWenKai-Medium.ttf", "~/.fonts/LXGWWenKai-Regular.ttf",
       "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]


def find_font():
    for p in CJK:
        if Path(p).expanduser().exists():
            return str(Path(p).expanduser())
    raise SystemExit("找不到中文字体（霞鹜文楷）")


def page_files(spec, folder, fmt, n, name):
    prefix = spec.get("prefix", "复刻图")
    base = f"{prefix}{n:02d}-{name}"
    for ext in ([fmt] if fmt else ["png", "jpg"]):
        p = folder / f"{base}.{ext}"
        if p.exists():
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--clean", required=True, type=Path, help="无 UI 版目录")
    ap.add_argument("--ui", required=True, type=Path, help="有 UI 版目录")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--format", choices=["jpg", "png"], default="jpg")
    a = ap.parse_args()

    spec = json.loads(a.spec.read_text(encoding="utf-8"))
    W, H = spec.get("canvas", [1440, 3200])
    cols = 5
    tw = 300
    th = round(tw * H / W)
    gap, margin, header, row_label = 32, 52, 132, 130
    pairs_expected = len([p for p in spec["pages"]
                          if page_files(spec, a.clean, a.format, p["n"], p["name"])
                          and page_files(spec, a.ui, a.format, p["n"], p["name"])])
    rows_per_version = max(1, (pairs_expected + cols - 1) // cols)
    sw = margin * 2 + cols * tw + (cols - 1) * gap
    sh = margin + header + 2 * rows_per_version * (th + row_label) + gap + margin
    sheet = Image.new("RGB", (sw, sh), (241, 222, 203))
    d = ImageDraw.Draw(sheet)
    fnt = find_font()
    f_title, f_sub = ImageFont.truetype(fnt, 44), ImageFont.truetype(fnt, 23)
    f_tag, f_name = ImageFont.truetype(fnt, 25), ImageFont.truetype(fnt, 21)

    d.text((margin, margin - 6), spec["title"], font=f_title, fill=(58, 46, 42))
    d.text((margin, margin + 62), spec.get("subtitle", ""), font=f_sub, fill=(120, 100, 92))

    pairs = []
    for pg in spec["pages"]:
        cp = page_files(spec, a.clean, a.format, pg["n"], pg["name"])
        up = page_files(spec, a.ui, a.format, pg["n"], pg["name"])
        if not cp or not up:
            print(f"[skip] 第 {pg['n']:02d} 页缺图: clean={bool(cp)} ui={bool(up)}")
            continue
        pairs.append((pg, cp, up))
    if not pairs:
        raise SystemExit("没有成对的干净图 / 有 UI 图，先跑 phone_mockup.py 与 ui_overlay.py")

    top = margin + header
    for row, key in enumerate(("clean", "ui")):
        y_start = top + row * (rows_per_version * (th + row_label) + gap)
        d.text((margin, y_start - 44), "无 UI 版 · 干净壁纸" if row == 0 else "有 UI 版 · 装机预览（只看不发）",
               font=f_tag, fill=(88, 66, 56))
        for i, (pg, cp, up) in enumerate(pairs):
            src = cp if key == "clean" else up
            im = Image.open(src).convert("RGB")
            im.thumbnail((tw, th), Image.LANCZOS)
            tile = Image.new("RGB", (tw, th), (232, 216, 200))
            tile.paste(im, ((tw - im.width) // 2, (th - im.height) // 2))
            x = margin + (i % cols) * (tw + gap)
            y = y_start + (i // cols) * (th + row_label)
            sheet.paste(tile, (x, y))
            tag = "无 UI" if row == 0 else ("锁屏" if pg.get("overlay", "lock") == "lock" else "主屏")
            d.rounded_rectangle((x + 8, y + 8, x + 8 + 66 + 16 * len(tag), y + 46), 10,
                                fill=(58, 46, 42))
            d.text((x + 16, y + 13), tag, font=f_tag, fill=(255, 248, 238))
            label = f"{pg['n']:02d} {pg['name']}"
            box = d.textbbox((0, 0), label, font=f_name)
            tw_l = box[2] - box[0]
            d.rounded_rectangle((x + tw - tw_l - 22, y + th - 46, x + tw - 8, y + th - 8), 8,
                                fill=(241, 222, 203))
            d.text((x + tw - tw_l - 15, y + th - 42), label, font=f_name, fill=(58, 46, 42))

    a.out.parent.mkdir(parents=True, exist_ok=True)
    if a.out.suffix.lower() in (".jpg", ".jpeg"):
        sheet.save(a.out, "JPEG", quality=92, subsampling=0)
    else:
        sheet.save(a.out, "PNG")
    print(f"[compare] {a.out}  {len(pairs)} 页 × 2 排")


if __name__ == "__main__":
    main()
