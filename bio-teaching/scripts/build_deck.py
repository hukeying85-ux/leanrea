#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把课件 md 排版成 PPT Master 可转换的 SVG 页，并导出原生 PPTX。

两层分工：
    md      = 讲什么（要点 + 备注）
    plan.json = 长什么样（每页 layout / 配图 / kicker / 说明）

视觉语言（v2，"单墨版画"）：
    一套课件只用两种颜色——暖纸 #F4EFE4 与深松墨 #14302F，赤陶 #B8452A 只做一两处强调；
    所有配图先经 scripts/duotone.py 压成同一套双色版画（浅版/深版两个版本），
    因此照片、3D 渲染、水彩插画在版面上读起来是**同一套图版**，而不是四种材料拼贴。

用法：
    python3 scripts/build_deck.py --md <课件.md> --plan <plan.json> --out <目录> \
        --images <已 duotone 的图目录> --skill <ppt-master skill 目录>
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

W, H = 1280, 720
M = 76                      # 版心边距
PAPER = "#F4EFE4"
INK = "#14302F"
INK2 = "#4E625F"
RULE = "#D5CCBA"
RUST = "#B8452A"
TEAL = "#2C6157"
DARK = "#0C1A1B"
SERIF = "Songti SC, STSong, SimSun, serif"
SANS = "PingFang SC, Microsoft YaHei, Noto Sans SC, sans-serif"


# ---------------------------------------------------------------- 基础图元
def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def text_w(s: str, size: float) -> float:
    return sum((0.52 if ord(c) < 128 else 1.0) for c in s) * size


def wrap(s: str, size: float, max_w: float) -> list[str]:
    lines, cur = [], ""
    for ch in s:
        if text_w(cur + ch, size) > max_w and cur:
            lines.append(cur)
            cur = ch.lstrip() if ch == " " else ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def fit(s: str, size: float, max_w: float, max_lines: int, floor=14) -> tuple[float, list[str]]:
    while size > floor:
        ls = wrap(s, size, max_w)
        if len(ls) <= max_lines:
            return size, ls
        size -= 2
    return size, wrap(s, size, max_w)


def T(x, y, s, size=20, fill=INK, font=SANS, weight=400, anchor="start",
      spacing=None, opacity=None, italic=False) -> str:
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    sp = f' letter-spacing="{spacing}"' if spacing else ""
    op = f' fill-opacity="{opacity}"' if opacity is not None else ""
    it = ' font-style="italic"' if italic else ""
    return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}"{a}{sp}{op}{it}>{esc(s)}</text>')


def R(x, y, w, h, fill, opacity=None, stroke=None, sw=1) -> str:
    op = f' fill-opacity="{opacity}"' if opacity is not None else ""
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"{op}{st}/>'


def L(x1, y1, x2, y2, color=RULE, sw=1, opacity=None) -> str:
    op = f' stroke-opacity="{opacity}"' if opacity is not None else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="{sw}"{op}/>')


def IMG(name: str, x, y, w, h, variant="light", images_dir="../images") -> str:
    stem = f"{name}-{variant}"
    ext = ".jpg" if Path(images_dir, stem + ".jpg").exists() or True else ".jpg"
    return (f'<image href="{images_dir}/{stem}{ext}" x="{x}" y="{y}" '
            f'width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice"/>')


def kicker(s: str, x=M, y=96, color=RUST) -> str:
    return "".join([
        R(x, y - 9, 7, 7, color),
        T(x + 16, y, s, 13, color, SANS, 500, spacing=3.2),
    ])


def folio(i: int, total: int, label: str) -> str:
    return "".join([
        L(M, 654, W - M, 654, RULE, 1),
        T(M, 682, label, 12, INK2, SANS, 400, spacing=1.6, opacity=0.8),
        T(W - M, 682, f"{i:02d} — {total:02d}", 12, INK2, SANS, 400, anchor="end",
          spacing=1.2, opacity=0.8),
    ])


def plate_caption(text: str, x, y, color=INK2) -> str:
    return T(x, y, text, 12.5, color, SERIF, 400, spacing=1.2, opacity=0.85, italic=True)


# ---------------------------------------------------------------- 版式
def lay_cover(p, meta, ctx):
    e = [R(0, 0, W, H, PAPER)]
    ix = 700
    e.append(IMG(p["image"], ix, 0, W - ix, H, "light"))
    e.append(R(ix - 8, 0, 8, H, PAPER))
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    t = p.get("title") or meta["title"]
    size, lines = fit(t, 58, 580, 3)
    y = 268 - (len(lines) - 1) * size * 0.55
    for ln in lines:
        e.append(T(M, y, ln, size, INK, SERIF, 700))
        y += size * 1.16
    e.append(L(M, y + 8, M + 96, y + 8, RUST, 3))
    if p.get("subtitle"):
        for k, ln in enumerate(wrap(p["subtitle"], 20, 540)):
            e.append(T(M, y + 62 + k * 32, ln, 20, INK2, SANS, 400))
    e.append(T(M, 640, meta["meta"], 12.5, INK2, SANS, 400, spacing=1.4, opacity=0.85))
    return e


def lay_plate_full(p, meta, ctx):
    e = [R(0, 0, W, H, DARK), IMG(p["image"], 0, 0, W, H, "ink")]
    e.append(R(0, 250, W, H - 250, DARK, 0.55))
    e.append(T(M, 420, p.get("kicker", ""), 13, PAPER, SANS, 500, spacing=3.2))
    size, lines = fit(p.get("title") or "", 50, 980, 2)
    y = 490
    for ln in lines:
        e.append(T(M, y, ln, size, PAPER, SERIF, 700))
        y += size * 1.16
    if p.get("caption"):
        e.append(plate_caption(p["caption"], M, 640, PAPER))
    return e


def lay_plate_side(p, meta, ctx):
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    tw = 560
    size, tl = fit(p["title"], 40, tw, 3)
    y = 190
    for ln in tl:
        e.append(T(M, y, ln, size, INK, SERIF, 700))
        y += size * 1.12
    y += 30
    for i, b in enumerate(p["bullets"], 1):
        e.append(T(M, y, f"{i:02d}", 15, RUST, SANS, 500, spacing=1))
        bs, bl = fit(b, 21, tw - 54, 2)
        yy = y
        for ln in bl:
            e.append(T(M + 46, yy, ln, bs, INK, SANS, 400))
            yy += bs * 1.5
        y = yy + 24
        if i < len(p["bullets"]):
            e.append(L(M + 46, y - 18, M + tw, y - 18, RULE, 0.9))
    e.append(IMG(p["image"], 720, 150, 484, 400, "light"))
    e.append(R(720, 150, 484, 400, "none", stroke=RULE, sw=1))
    if p.get("caption"):
        e.append(plate_caption(p["caption"], 720, 584))
    return e


def lay_hero(p, meta, ctx):
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    size, lines = fit(p.get("title") or "", 30, 900, 2)
    y = 176
    for ln in lines:
        e.append(T(M, y, ln, size, INK2, SANS, 400))
        y += size * 1.3
    big = p.get("big") or []
    x = M
    base = 470
    for it in big:
        s = it["text"]
        fs = it.get("size", 108)
        e.append(T(x, base, s, fs, it.get("color", INK), SERIF, 700))
        x += text_w(s, fs) + (it.get("gap", 40))
    e.append(L(M, base + 46, 820 if p.get("image") else W - M, base + 46, RULE, 1.2))
    if p.get("note"):
        for k, ln in enumerate(wrap(p["note"], 22, 720 if p.get("image") else 980)):
            e.append(T(M, base + 100 + k * 34, ln, 22, INK, SANS, 400))
    if p.get("image"):
        e.append(IMG(p["image"], 900, 300, 304, 240, "light"))
        e.append(R(900, 300, 304, 240, "none", stroke=RULE, sw=1))
        if p.get("caption"):
            e.append(plate_caption(p["caption"], 900, 570))
    return e


def lay_diagram(p, meta, ctx):
    """原生矢量能量图：两个谷、一个垭口、一条隧道。不用风景照当隐喻。"""
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    size, tl = fit(p.get("title") or "", 34, 1040, 1)
    e.append(T(M, 168, tl[0], size, INK, SERIF, 700))

    x0, x1 = 180, 1120
    yb, yt = 540, 250
    # 底轴
    e.append(L(x0 - 30, yb, x1 + 10, yb, INK, 1.4))
    e.append(T(x1 + 10, yb + 30, p.get("xlabel", "反应进程"), 15, INK2, SANS, 400, anchor="end"))
    e.append(T(x0 - 36, yt - 24, p.get("ylabel", "能量"), 15, INK2, SANS, 400, anchor="end"))
    # 山形：起 → 峰 → 落 → 小峰 → 落
    peak = p.get("peak", 0.9)
    py = yb - (yb - yt) * peak
    hill = (f'M{x0},{yb} C{x0 + 90},{yb} {x0 + 150},{py} {x0 + 300},{py} '
            f'C{x0 + 430},{py} {x0 + 470},{yb} {x0 + 560},{yb} '
            f'C{x0 + 640},{yb} {x0 + 700},{yb - 30} {x0 + 760},{yb - 30} '
            f'L{x1},{yb - 30}')
    e.append(f'<path d="{hill}" fill="none" stroke="{INK}" stroke-width="3.2" stroke-linecap="round"/>')
    # 活化能标注
    ax = x0 + 170
    e.append(L(ax, yb, ax, py, RUST, 1.4))
    e.append(f'<path d="M{ax - 5},{py + 12} L{ax},{py} L{ax + 5},{py + 12}" fill="none" stroke="{RUST}" stroke-width="1.4"/>')
    e.append(f'<path d="M{ax - 5},{yb - 12} L{ax},{yb} L{ax + 5},{yb - 12}" fill="none" stroke="{RUST}" stroke-width="1.4"/>')
    e.append(T(ax + 14, (yb + py) / 2, p.get("ann", "活化能"), 17, RUST, SANS, 500))
    # 催化剂：垭口降低
    if p.get("catalyst", True):
        cpy = py + 74
        e.append(f'<path d="M{x0 + 110},{yb - 40} C{x0 + 170},{cpy} {x0 + 250},{cpy} {x0 + 300},{cpy} '
                 f'C{x0 + 350},{cpy} {x0 + 430},{yb - 40} {x0 + 470},{yb - 40}" fill="none" '
                 f'stroke="{TEAL}" stroke-width="1.6" stroke-dasharray="7 6" stroke-linecap="round"/>')
        e.append(T(x0 + 320, cpy - 18, p.get("catalyst_label", "无机催化剂：降一点"), 15, TEAL, SANS, 400))
    # 隧道：酶
    if p.get("tunnel", True):
        ty = yb - 96
        e.append(L(x0 + 60, ty, x0 + 720, ty, RUST, 2.6, 0.95))
        e.append(T(x0 + 60, ty - 16, p.get("tunnel_label", "酶：打一条隧道"), 15, RUST, SANS, 500))
    for cap, cx in ((p.get("left", "反应物"), x0 + 70), (p.get("right", "产物"), x1 - 90)):
        e.append(T(cx, yb + 34, cap, 14, INK2, SANS, 400, spacing=1.2))
    return e


def lay_chart(p, meta, ctx):
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    size, tl = fit(p["title"], 32, 640, 2)
    y = 172
    for ln in tl:
        e.append(T(M, y, ln, size, INK, SERIF, 700))
        y += size * 1.15
    X0, Y0, X1, Y1 = 190, 560, 740, 260
    e.append(L(X0, Y1 - 40, X0, Y0, INK, 1.2))
    e.append(L(X0, Y0, X1 + 20, Y0, INK, 1.2))
    e.append(T(X0 - 16, Y1 - 46, p.get("ylabel", ""), 15, INK2, SANS, 400, anchor="end"))
    e.append(T(X1 + 20, Y0 + 30, p.get("xlabel", ""), 15, INK2, SANS, 400, anchor="end"))

    def path_for(peak, baseline=0.12, cutoff=None):
        pts = []
        for i in range(81):
            t = i / 80
            if cutoff is not None and t > cutoff:
                v = 0.03
            else:
                u = min(t / 0.55, 1.0)
                v = baseline + (peak - baseline) * (u ** 1.8)
                if t > 0.55:
                    v = baseline + (peak - baseline) * (1 - (t - 0.55) * 0.12)
            pts.append((X0 + 10 + t * (X1 - X0 - 10),
                        Y0 - 16 - (v - 0.03) * (Y0 - Y1 - 16)))
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    for s in p["series"]:
        dash = ' stroke-dasharray="9 7"' if s.get("dash") else ""
        e.append(f'<path d="{path_for(s["peak"], s.get("baseline", 0.12), s.get("cutoff"))}" '
                 f'fill="none" stroke="{s["color"]}" stroke-width="2.6"{dash} stroke-linecap="round"/>')
    ly = 300
    for s in p["series"]:
        dash = ' stroke-dasharray="9 7"' if s.get("dash") else ""
        e.append(f'<line x1="800" y1="{ly}" x2="852" y2="{ly}" stroke="{s["color"]}" stroke-width="2.6"{dash}/>')
        e.append(T(866, ly + 6, s["name"], 18, INK, SANS, 400))
        ly += 42
    if p.get("note"):
        e.append(L(800, ly + 4, 1204, ly + 4, RULE, 1))
        yy = ly + 40
        for raw in p["note"].split("\n"):
            for ln in wrap(raw, 17, 400):
                e.append(T(800, yy, ln, 17, INK2, SANS, 400))
                yy += 27
    return e


def lay_table(p, meta, ctx):
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    size, tl = fit(p["title"], 34, 1020, 2)
    y = 170
    for ln in tl:
        e.append(T(M, y, ln, size, INK, SERIF, 700))
        y += size * 1.12
    rows = p["table"]
    ncol = max(len(r) for r in rows)
    cw = (W - 2 * M) / ncol
    y += 30
    e.append(L(M, y, W - M, y, INK, 2))
    y += 38
    for ri, row in enumerate(rows):
        for ci in range(ncol):
            val = row[ci] if ci < len(row) else ""
            if ri == 0:
                e.append(T(M + ci * cw + 10, y, val, 13, RUST, SANS, 500, spacing=2.4))
            else:
                e.append(T(M + ci * cw + 10, y, val, 20, INK,
                           SERIF if ci == 0 else SANS, 700 if ci == 0 else 400))
        y += 56
        e.append(L(M, y - 24, W - M, y - 24, RULE, 0.9))
    if p.get("caption"):
        e.append(plate_caption(p["caption"], M, y + 6))
    return e


def lay_compare(p, meta, ctx):
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    size, tl = fit(p["title"], 34, 1020, 2)
    y = 168
    for ln in tl:
        e.append(T(M, y, ln, size, INK, SERIF, 700))
        y += size * 1.12
    y += 44
    cols = p["cols"]
    cw = (W - 2 * M) / len(cols)
    if len(cols) == 2:
        e.append(L(W / 2, y - 26, W / 2, y + 236, RULE, 1))
    for ci, c in enumerate(cols):
        x = M + ci * cw + (0 if ci == 0 else 34)
        e.append(T(x, y, c["label"], 13, RUST if ci == 0 else TEAL, SANS, 500, spacing=2.4))
        e.append(T(x, y + 56, c["head"], 32, INK, SERIF, 700))
        yy = y + 106
        for b in c.get("bullets", []):
            for ln in wrap(b, 18, cw - 70)[:2]:
                e.append(T(x, yy, ln, 18, INK2, SANS, 400))
                yy += 28
            yy += 8
    return e


def lay_checklist(p, meta, ctx):
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    size, tl = fit(p["title"], 34, 1020, 2)
    y = 168
    for ln in tl:
        e.append(T(M, y, ln, size, INK, SERIF, 700))
        y += size * 1.12
    y += 48
    for item in p["pairs"]:
        e.append(T(M, y, "✗", 24, RUST, SANS, 700))
        for ln in wrap(item["wrong"], 22, 430)[:2]:
            e.append(T(M + 44, y, ln, 22, INK2, SANS, 400))
            y += 30
        e.append(T(600, y - 30, "→", 22, TEAL, SANS, 700))
        yy = y - 30
        for ln in wrap(item["right"], 22, 540)[:2]:
            e.append(T(646, yy, ln, 22, INK, SANS, 500))
            yy += 30
        y = max(y, yy) + 26
        e.append(L(M, y - 16, W - M, y - 16, RULE, 0.9))
    return e


def lay_quote(p, meta, ctx):
    e = [R(0, 0, W, H, PAPER)]
    has_img = bool(p.get("image"))
    if has_img:
        e.append(IMG(p["image"], 720, 0, W - 720, H, "light"))
        e.append(R(712, 0, 8, H, PAPER))
    e.append(kicker(p.get("kicker") or meta["kicker"], M, 150))
    lines_in = p.get("lines") or [p.get("title") or ""]
    y = 320
    for ln in lines_in:
        size, ls = fit(ln, 48, 560 if has_img else 1000, 2)
        for s in ls:
            e.append(T(M, y, s, size, INK, SERIF, 700))
            y += size * 1.2
        y += 14
    e.append(L(M, y + 16, M + 88, y + 16, RUST, 3))
    if p.get("note"):
        for k, ln in enumerate(wrap(p["note"], 18, 520 if has_img else 900)):
            e.append(T(M, y + 70 + k * 28, ln, 18, INK2, SANS, 400))
    return e


def lay_section(p, meta, ctx):
    e = [R(0, 0, W, H, DARK)]
    if p.get("image"):
        e.append(IMG(p["image"], 0, 0, W, H, "ink"))
        e.append(R(0, 0, W, H, DARK, 0.55))
    e.append(T(M, 250, p.get("num", ""), 120, RUST, SERIF, 700))
    size, lines = fit(p["title"], 46, 900, 2)
    y = 380
    for ln in lines:
        e.append(T(M, y, ln, size, PAPER, SERIF, 700))
        y += size * 1.2
    e.append(L(M, y + 4, M + 96, y + 4, PAPER, 3))
    if p.get("subtitle"):
        e.append(T(M, y + 62, p["subtitle"], 19, PAPER, SANS, 400, opacity=0.82))
    return e


def lay_statement(p, meta, ctx):
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    lines_in = p.get("lines") or [p.get("title") or ""]
    y = 300
    for ln in lines_in:
        size, ls = fit(ln, 50, 980, 2)
        for s in ls:
            e.append(T(M, y, s, size, INK, SERIF, 700))
            y += size * 1.2
        y += 12
    e.append(L(M, y + 10, M + 300, y + 10, RULE, 2))
    if p.get("note"):
        for k, ln in enumerate(wrap(p["note"], 20, 940)):
            e.append(T(M, y + 64 + k * 30, ln, 20, INK2, SANS, 400))
    if p.get("image"):
        e.append(IMG(p["image"], 900, 440, 304, 190, "light"))
        e.append(R(900, 440, 304, 190, "none", stroke=RULE, sw=1))
    return e


LAYOUTS = {
    "cover": lay_cover, "plate": lay_plate_full, "plate_side": lay_plate_side,
    "hero": lay_hero, "diagram": lay_diagram, "chart": lay_chart,
    "table": lay_table, "compare": lay_compare, "checklist": lay_checklist,
    "quote": lay_quote, "section": lay_section, "statement": lay_statement,
}
NO_FOLIO = {"cover", "plate", "section", "quote"}


# ---------------------------------------------------------------- 解析 md
def parse_md(path: Path):
    t = path.read_text(encoding="utf-8")
    meta = {"title": "", "subtitle": "", "kicker": "", "meta": ""}
    slides, cur = [], None
    for ln in t.splitlines():
        if ln.startswith("# ") and not meta["title"]:
            meta["title"] = ln[2:].strip()
            continue
        if ln.startswith(">") and not meta["subtitle"]:
            meta["subtitle"] = ln.lstrip("> ").strip()
            continue
        m = re.match(r"^##\s+(\d+)\s+(.*)$", ln)
        if m:
            if cur:
                slides.append(cur)
            cur = {"num": m.group(1), "title": m.group(2).strip(),
                   "bullets": [], "table": [], "note": ""}
            continue
        if cur is None:
            continue
        if ln.startswith("<!--"):
            n = re.search(r"note:\s*(.*?)\s*-->", ln)
            if n:
                cur["note"] = n.group(1)
            continue
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c or "---") for c in cells):
                continue
            cur["table"].append(cells)
            continue
        if ln.startswith("- "):
            cur["bullets"].append(ln[2:].strip())
            continue
        if ln.strip():
            cur["bullets"].append(ln.strip())
    if cur:
        slides.append(cur)
    return meta, slides


def choose_layout(s, spec):
    if spec.get("layout"):
        return spec["layout"]
    if s["table"]:
        return "table"
    if len(s["bullets"]) <= 2:
        return "statement"
    return "plate_side"


# ---------------------------------------------------------------- 构建
def build(md: Path, plan: Path, out: Path, images: Path, skill: Path) -> Path:
    meta, slides = parse_md(md)
    p = json.loads(plan.read_text(encoding="utf-8")) if plan.exists() else {"pages": []}
    specs = p.get("pages", [])
    meta["kicker"] = p.get("kicker", meta["kicker"] or meta["title"])
    meta["meta"] = p.get("meta", "")

    svgdir = out / "svg_output"
    if svgdir.exists():
        shutil.rmtree(svgdir)
    svgdir.mkdir(parents=True)
    imgdir = out / "images"
    imgdir.mkdir(exist_ok=True)
    for f in images.glob("*.*"):
        shutil.copy2(f, imgdir / f.name)

    total = len(slides)
    for i, s in enumerate(slides, start=1):
        spec = specs[i - 1] if i - 1 < len(specs) else {}
        page = dict(s)
        page.update({k: v for k, v in spec.items() if k != "layout"})
        if not page.get("table") and s["table"]:
            page["table"] = s["table"]
        lay = choose_layout(s, spec)
        body = LAYOUTS[lay](page, meta, {"i": i, "total": total})
        if lay not in NO_FOLIO:
            body.append(folio(i, total, meta["title"]))

        bg, rest = None, body
        if body and "width=\"1280\" height=\"720\"" in body[0]:
            bg, rest = body[0], body[1:]
        if bg:
            bg = bg.replace("/>", ' id="bg" data-pptx-role="background"/>', 1)
        role = ("cover" if i == 1 else "section" if lay == "section"
                else "ending" if i == total else "content")
        parts = ([bg] if bg else []) + [
            f'<g id="content" data-pptx-bounds="0 0 {W} {H}">'] + rest + ["</g>"]
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" '
               'xmlns:xlink="http://www.w3.org/1999/xlink" lang="zh-CN" '
               f'viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
               f'font-family="{SANS}" data-pptx-page-role="{role}">\n'
               + "\n".join(parts) + "\n</svg>\n")
        name = f"{i:02d}-{re.sub(r'[^0-9A-Za-z一-龥]+', '', page['title'])[:12]}.svg"
        (svgdir / name).write_text(svg, encoding="utf-8")

    notes_dir = out / "notes"
    notes_dir.mkdir(exist_ok=True)
    blocks = [f"# {i:02d}_{s['title']}\n\n{(s.get('note') or '')}" for i, s in enumerate(slides, 1)]
    (notes_dir / "total.md").write_text("\n\n---\n\n".join(blocks) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, str(skill / "scripts/total_md_split.py"), str(out)],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    subprocess.run([sys.executable, str(skill / "scripts/compact_svg_styles.py"),
                    str(svgdir), "--inplace"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(skill / "scripts/svg_quality_checker.py"),
                    str(out), "--quick-generate", "--canonical-authoring",
                    "--stage", "final", "--json"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    pptx = out / (md.stem + ".pptx")
    r = subprocess.run([sys.executable, str(skill / "scripts/svg_to_pptx.py"),
                        str(out), "--quick-generate", "--primary-language", "zh-CN",
                        "--with-notes", "-o", str(pptx)], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-1200:])
        print(r.stderr[-1200:], file=sys.stderr)
        sys.exit(r.returncode)
    for line in r.stdout.splitlines():
        if "POSTFLIGHT" in line or "[Done]" in line or "Slides:" in line:
            print(line.strip())
    write_preview(out, meta, total)
    return pptx


PREVIEW = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{title} · 版式预览</title>
<style>
:root{{--paper:#F4EFE4;--ink:#14302F;--rust:#B8452A}}
body{{margin:0;background:#0b1314;color:#e9e3d7;font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif}}
header{{padding:30px 40px 6px}} h1{{font-size:21px;margin:0 0 6px;font-weight:600;letter-spacing:.5px}}
p.meta{{margin:0;color:#8b9a94;font-size:12.5px;letter-spacing:1px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(470px,1fr));gap:20px;padding:26px 40px 64px}}
figure{{margin:0;background:#152023;border-radius:3px;overflow:hidden}}
img{{width:100%;display:block}}
figcaption{{font-size:11.5px;color:#8b9a94;padding:7px 10px;letter-spacing:.6px}}
</style></head><body>
<header><h1>{title}</h1><p class="meta">{meta} · 共 {total} 页 · 单墨版画版式 · 文字/图片/曲线均为原生对象</p></header>
<div class="grid">
{items}
</div></body></html>"""


def write_preview(out: Path, meta: dict, total: int) -> None:
    files = sorted((out / "svg_output").glob("*.svg"))
    items = "\n".join(
        f'<figure><img src="svg_output/{f.name}" alt="{esc(f.stem)}">'
        f'<figcaption>{esc(f.stem)}</figcaption></figure>' for f in files)
    (out / "preview.html").write_text(
        PREVIEW.format(title=esc(meta["title"]), meta=esc(meta["meta"]), total=total,
                       items=items), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True)
    ap.add_argument("--plan", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--skill", default="/home/user/ppt-master/skills/ppt-master")
    a = ap.parse_args()
    pptx = build(Path(a.md), Path(a.plan) if a.plan else Path(a.md).with_suffix(".plan.json"),
                 Path(a.out), Path(a.images), Path(a.skill))
    print(f"[ok] {pptx}")


if __name__ == "__main__":
    main()
