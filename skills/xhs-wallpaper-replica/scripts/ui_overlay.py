#!/usr/bin/env python3
"""ui_overlay.py —— 给任意画幅的干净壁纸叠 iOS 锁屏 / 主屏层（「有 UI 版」预览）。

phone_mockup.py 的几何常量写死在 1440×3200（9:20）。复刻 9:16（1440×2560）这类画幅时，
直接用它会被裁切；这个脚本按 spec.canvas 等比缩放同一套几何，叠出 1:1 同画幅的预览。

用法：
  python3 scripts/ui_overlay.py SPEC.json --in 干净壁纸目录 --out 预览目录 [--format jpg|png]
  每页用 spec.pages[].overlay（lock / home）决定叠哪一层；--only lock 可强制全部按锁屏叠。

输出：OUT/<与原文件同名>；文件名前缀与 spec.prefix 一致。
依赖：Pillow；锁屏时钟字体 Inter（~/.fonts/Inter-Variable.ttf 或 --clock-font）。
"""
import argparse
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# 1440×3200 实测几何（与 SKILL.md 的锁屏几何表一致），下面按画幅等比缩放
BASE = (1440, 3200)
DATE_CY, DATE_SIZE, DATE_WGHT = 319, 78, 600
TIME_CY, TIME_SIZE, TIME_WGHT = 553, 336, 700
BTN_R, BTN_CY, BTN_CX = 92, 2940, (231, 1209)
BAR = (468, 3129, 971, 3147)
ICON, ICON_R = 244, 54
ICON_CX = (212, 548, 892, 1228)
ICON_ROWS_CY = (300, 602)
DOCK_CY = 2960

CLOCK_CANDS = ["~/.fonts/Inter-Variable.ttf", "~/.fonts/Inter.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def find_clock(explicit):
    for p in ([explicit] if explicit else []) + CLOCK_CANDS:
        if p and Path(p).expanduser().exists():
            return str(Path(p).expanduser())
    raise SystemExit("找不到时钟字体 Inter：--clock-font 或放一份到 ~/.fonts/Inter-Variable.ttf")


def font(path, size, wght=None):
    f = ImageFont.truetype(path, size)
    if wght is not None:
        try:
            vals = []
            for ax in f.get_variation_axes():
                name = ax["name"].decode() if isinstance(ax["name"], bytes) else ax["name"]
                vals.append(wght if "eight" in name else
                            (ax["maximum"] if "ptical" in name else ax["default"]))
            f.set_variation_by_axes(vals)
        except Exception:
            pass
    return f


def draw_centered(img, text, f, cx, cy, fill=(255, 255, 255, 248)):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    d.text((cx - (l + r) / 2, cy - (t + b) / 2), text, font=f, fill=fill)
    img.alpha_composite(layer)


def rounded_mask(size, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), r, fill=255)
    return m


def glass_patch(base, box, blur, white_alpha, dark=1.0):
    patch = base.crop(box).filter(ImageFilter.GaussianBlur(blur))
    if dark != 1.0:
        patch = Image.eval(patch, lambda v: int(v * dark))
    if white_alpha:
        patch = Image.blend(patch, Image.new("RGB", patch.size, (255, 255, 255)), white_alpha)
    return patch


def flashlight(d, cx, cy, s, fill=(255, 255, 255, 255)):
    P = lambda x, y: (cx + x * s, cy + y * s)
    d.polygon([P(-30, -52), P(30, -52), P(17, -14), P(-17, -14)], fill=fill)
    d.rounded_rectangle([P(-17, -8), P(17, 54)], radius=max(1, 12 * s), fill=fill)
    d.rectangle([P(-30, -62), P(30, -52)], fill=fill)
    d.ellipse([P(-7, -46), P(7, -32)], fill=(0, 0, 0, 0))


def camera(d, cx, cy, s, fill=(255, 255, 255, 255)):
    P = lambda x, y: (cx + x * s, cy + y * s)
    d.rounded_rectangle([P(-52, -30), P(52, 42)], radius=max(1, 14 * s), fill=fill)
    d.rounded_rectangle([P(-24, -46), P(24, -24)], radius=max(1, 8 * s), fill=fill)
    d.ellipse([P(-24, -18), P(24, 30)], fill=(0, 0, 0, 0))
    d.ellipse([P(-15, -9), P(15, 21)], fill=fill)


def lock_layer(base, date, time, clock, k, ky):
    img = base.convert("RGBA")
    r = round(BTN_R * k)
    for cx0 in BTN_CX:
        cx, cy = round(cx0 * k), round(BTN_CY * ky)
        box = (cx - r, cy - r, cx + r, cy + r)
        patch = glass_patch(img.convert("RGB"), box, blur=max(6, round(28 * k)), white_alpha=0.0, dark=0.74)
        m = Image.new("L", patch.size, 0)
        ImageDraw.Draw(m).ellipse((0, 0, patch.size[0] - 1, patch.size[1] - 1), fill=255)
        img.paste(patch, box[:2], m)
    glyphs = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(glyphs)
    flashlight(d, round(BTN_CX[0] * k), round(BTN_CY * ky), 0.88 * k)
    camera(d, round(BTN_CX[1] * k), round(BTN_CY * ky), 0.88 * k)
    img.alpha_composite(glyphs)
    draw_centered(img, date, font(clock, round(DATE_SIZE * k), DATE_WGHT),
                  img.width / 2, DATE_CY * ky)
    draw_centered(img, time, font(clock, round(TIME_SIZE * k), TIME_WGHT),
                  img.width / 2, TIME_CY * ky)
    bar = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(bar).rounded_rectangle(
        (round(BAR[0] * k), round(BAR[1] * ky), round(BAR[2] * k), round(BAR[3] * ky)),
        radius=max(2, round(9 * k)), fill=(255, 255, 255, 235))
    img.alpha_composite(bar)
    return img.convert("RGB")


def home_layer(base, k, ky):
    img = base.convert("RGB")
    icon, icon_r = round(ICON * k), round(ICON_R * k)
    cells = [(round(cx * k), round(cy * ky)) for cy in ICON_ROWS_CY for cx in ICON_CX]
    cells += [(round(cx * k), round(DOCK_CY * ky)) for cx in ICON_CX]
    mask = rounded_mask((icon, icon), icon_r)
    edge = Image.new("RGBA", (icon, icon), (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle((1, 1, icon - 2, icon - 2), icon_r,
                                           outline=(255, 255, 255, 140), width=max(2, round(3 * k)))
    for cx, cy in cells:
        box = (cx - icon // 2, cy - icon // 2, cx + icon // 2, cy + icon // 2)
        patch = glass_patch(img, box, blur=max(8, round(40 * k)), white_alpha=0.42).convert("RGBA")
        patch.alpha_composite(edge)
        img.paste(patch.convert("RGB"), box[:2], mask)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--in", dest="src", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--clock-font", default=None)
    ap.add_argument("--format", choices=["jpg", "png"], default="jpg")
    ap.add_argument("--only", choices=["lock", "home"], default=None,
                    help="强制全部页按这一层叠（默认读 spec 每页的 overlay）")
    ap.add_argument("--date", default=None)
    ap.add_argument("--time", default=None)
    a = ap.parse_args()

    spec = json.loads(a.spec.read_text(encoding="utf-8"))
    W, H = spec.get("canvas", [1440, 3200])
    k, ky = W / BASE[0], H / BASE[1]
    clock = find_clock(a.clock_font)
    date = a.date or spec.get("date", "Friday, November 6")
    time = a.time or spec.get("time", "05:20")
    prefix = spec.get("prefix", "复刻图")
    a.out.mkdir(parents=True, exist_ok=True)

    for pg in spec["pages"]:
        name = f"{prefix}{pg['n']:02d}-{pg['name']}"
        src = None
        for ext in ("png", "jpg"):
            p = a.src / f"{name}.{ext}"
            if p.exists():
                src = p
                break
        if not src:
            print(f"[skip] {a.src}/{name}.* 不存在")
            continue
        base = Image.open(src).convert("RGB")
        if base.size != (W, H):
            print(f"[warn] {src.name} 是 {base.size}，spec canvas 是 {(W, H)}")
        layer = a.only or pg.get("overlay", "lock")
        out = lock_layer(base, date, time, clock, k, ky) if layer == "lock" else home_layer(base, k, ky)
        dst = a.out / f"{name}.{a.format}"
        if a.format == "jpg":
            out.save(dst, "JPEG", quality=92, subsampling=0)
        else:
            out.save(dst, "PNG", compress_level=6)
        print(f"[ui] {dst.name}  {layer}")


if __name__ == "__main__":
    main()
