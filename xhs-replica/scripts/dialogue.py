#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dialogue.py —— 在成品图上合成「很简单的对话」

规则和 finish.py 一样铁：**图片模型一个字都不写**。
出图时只留空位，对话在这里用脚本画上去，
所以中文不会错字、不会糊、不会被模型画成伪字。

画面版式（每张都照这个来）
  顶部 16%   留白 → 上方气泡（布布说）
  中部       角色
  底部 22%   留白 → 下方气泡（一二答）+ 一行小英文

用法
    python3 dialogue.py spec.json

spec.json
    {
      "outdir": "out",
      "sheet":  "out/总图.jpg",
      "grain":  0.010,
      "items": [
        {"src": "k01.png", "name": "对话图01", "top": "今天的蛋煎糊了",
         "bottom": "糊了也好吃", "word": "BREAKFAST"}
      ]
    }
"""
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import json, sys, os, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import finish  # 复用裁切 / USM / 胶片分级 / 字体选择

TW, TH = 1080, 2280

INK = (58, 42, 34)          # 气泡里字的颜色：暖墨色，不用纯黑
PAPER = (252, 248, 241)     # 气泡纸色
OUTLINE = 5                 # 描边粗细
TOP_CY = 0.105              # 上气泡中心 y（比例）
BOT_CY = 0.855              # 下气泡中心 y
WORD_Y = 0.945              # 底部小英文 y


def bubble(draw, text, cy, font, tail_down=True, max_w=920):
    """画一个白底墨边对话气泡，尾巴指向角色。返回 (x0,y0,x1,y1)。"""
    tw, th = draw.textbbox((0, 0), text, font=font)[2:]
    padx, pady = 52, 36
    w = min(max_w, tw + padx * 2)
    h = th + pady * 2
    cx = TW // 2
    x0, y0 = cx - w // 2, int(cy - h // 2)
    x1, y1 = x0 + w, y0 + h

    # 尾巴先画，再压气泡本体，接缝就被盖住了
    t = 46
    if tail_down:
        tri = [(cx - t // 2, y1 - 6), (cx + t // 2, y1 - 6), (cx - 8, y1 + 38)]
    else:
        tri = [(cx - t // 2, y0 + 6), (cx + t // 2, y0 + 6), (cx + 8, y0 - 38)]
    draw.polygon(tri, fill=PAPER, outline=INK)
    draw.line([tri[0], tri[2]], fill=INK, width=OUTLINE)
    draw.line([tri[1], tri[2]], fill=INK, width=OUTLINE)

    draw.rounded_rectangle([x0, y0, x1, y1], radius=42, fill=PAPER,
                           outline=INK, width=OUTLINE)
    draw.text((cx - tw // 2, y0 + pady - 6), text, font=font, fill=INK)
    return x0, y0, x1, y1


def small_word(draw, word, font, im=None):
    """底部一行小英文——保持「每张都有英文元素」这条老规矩。

    颜色必须跟着背景走：亮底用暖墨，暗底用奶油白。
    第一版写死奶油白，结果早餐那张（亮场景）整行字糊在亮底里看不见。
    """
    tw = draw.textbbox((0, 0), word, font=font)[2]
    cx = TW // 2
    y = int(TH * WORD_Y)
    # 取这一行的背景亮度，决定用深字还是浅字
    ink_bg = 0.5
    if im is not None:
        band = np.asarray(im.convert("RGB"))[y - 20:y + 60, cx - 260:cx + 260]
        ink_bg = float(band.mean()) / 255.0 if band.size else 0.5
    col = (250, 244, 234) if ink_bg < 0.55 else (96, 74, 60)
    draw.line([cx - tw // 2 - 30, y - 26, cx + tw // 2 + 30, y - 26],
              fill=col, width=3)
    draw.text((cx - tw // 2, y), word, font=font, fill=col)


def make_sheet(paths, out, cols=5, tile_w=300):
    """把成品拼成一张总图，方便选首图。"""
    tw = TH * tile_w // TW
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (tile_w * cols, tw * rows), (246, 241, 234))
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB").resize((tile_w, tw), Image.LANCZOS)
        sheet.paste(im, ((i % cols) * tile_w, (i // cols) * tw))
    sheet.save(out, quality=90)
    return sheet.size


def main(spec_path):
    spec = json.load(open(spec_path, encoding="utf-8"))
    outdir = spec["outdir"]
    grain = spec.get("grain", 0.010)
    os.makedirs(outdir, exist_ok=True)

    f_text = finish.pick_font(62, lang="zh")
    f_word = finish.pick_font(40, lang="en")

    made = []
    for i, it in enumerate(spec["items"]):
        im = Image.open(it["src"]).convert("RGB")
        # 1 裁到 9:19  2 放大到 1080x2280  3 USM  4 胶片分级
        w, h = im.size
        tr = TW / TH
        if w / h > tr:
            nw = int(h * tr); im = im.crop(((w - nw) // 2, 0, (w + nw) // 2, h))
        else:
            nh = int(w / tr); top = int((h - nh) * 0.42)
            im = im.crop((0, top, w, top + nh))
        im = im.resize((TW, TH), Image.LANCZOS)
        im = im.filter(__import__("PIL.ImageFilter", fromlist=["x"]).UnsharpMask(2, 60, 3))
        im = finish.film_grade(im, grain=grain,
                               rng=np.random.default_rng(7 + i))

        d = ImageDraw.Draw(im)
        if it.get("top"):
            bubble(d, it["top"], TH * TOP_CY, f_text, tail_down=True)
        if it.get("bottom"):
            bubble(d, it["bottom"], TH * BOT_CY, f_text, tail_down=False)
        if it.get("word"):
            small_word(d, it["word"], f_word, im=im)

        out = os.path.join(outdir, it["name"] + ".png")
        im.save(out)
        made.append(out)
        print(f"{it['name']}: 上「{it.get('top','')}」 下「{it.get('bottom','')}」 "
              f"word={it.get('word','')} -> {im.size}")

    if spec.get("sheet"):
        s = make_sheet(sorted(made), spec["sheet"])
        print(f"sheet -> {spec['sheet']} {s}")


if __name__ == "__main__":
    main(sys.argv[1])
