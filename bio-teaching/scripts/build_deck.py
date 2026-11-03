#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 06-课件.md（或 03-课件.md）排版成 PPT Master 可转换的 SVG 页面，并调用其 svg_to_pptx 导出原生 PPTX。

为什么不再手写 python-pptx：
    PowerPoint 的"好看"来自版式（层级、留白、图与字的关系），不是文本框加粗。
    这里用 PPT Master（MIT，hugohe3/ppt-master）的 SVG→原生 DrawingML 通道：
    每页是一张 1280×720 的 SVG，文字仍是可编辑文本，图片是原生图片，
    表格/曲线是原生形状，而不是截图。

用法：
    python3 scripts/build_deck.py --md <课件.md> --plan <plan.json> --out <输出目录> \
        --images <图片目录> --skill <ppt-master skill 目录> [--title "…"]

plan.json：{"pages": [{"layout": "cover", "image": "tubes", "kicker": "第 5 章"}, …]}
    pages 与 md 里的 `## NN 标题` 一一对应；缺省项按 md 内容自动选版式。
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
PAPER = "#F7F3EC"
INK = "#16262A"
INK2 = "#4A5C60"
RULE = "#D8D0C0"
ACCENT = "#C2542F"
TEAL = "#2E6B66"
DARK = "#0F1B1F"
SERIF = "Songti SC, STSong, SimSun, serif"
SANS = "PingFang SC, Microsoft YaHei, Noto Sans SC, sans-serif"


# ---------------------------------------------------------------- helpers
def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def text_w(s: str, size: float) -> float:
    """粗略字宽：汉字 1em，ASCII 0.52em，全角标点 1em。"""
    w = 0.0
    for ch in s:
        if ord(ch) < 128:
            w += 0.52
        else:
            w += 1.0
    return w * size


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


def fit(s: str, size: float, max_w: float, max_lines: int) -> tuple[float, list[str]]:
    """字号从 size 往下试，直到行数不超过 max_lines（最小 16px）。"""
    while size > 16:
        ls = wrap(s, size, max_w)
        if len(ls) <= max_lines:
            return size, ls
        size -= 2
    return size, wrap(s, size, max_w)


def T(x, y, s, size=20, fill=INK, font=SANS, weight=400, anchor="start",
      spacing=None, opacity=None) -> str:
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    sp = f' letter-spacing="{spacing}"' if spacing else ""
    op = f' fill-opacity="{opacity}"' if opacity is not None else ""
    return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}"{a}{sp}{op}>{esc(s)}</text>')


def R(x, y, w, h, fill, opacity=None, stroke=None, sw=1) -> str:
    op = f' fill-opacity="{opacity}"' if opacity is not None else ""
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"{op}{st}/>'


def L(x1, y1, x2, y2, color=RULE, sw=1, opacity=None) -> str:
    op = f' stroke-opacity="{opacity}"' if opacity is not None else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="{sw}"{op}/>')


def IMG(name: str, x, y, w, h, images_dir: str = "../images") -> str:
    ext = next((e for e in (".jpg", ".png", ".jpeg") if
                Path(images_dir, name + e).exists()), ".jpg")
    return (f'<image href="{images_dir}/{name}{ext}" x="{x}" y="{y}" '
            f'width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice"/>')


def kicker(s: str, x=96, y=76) -> str:
    return T(x, y, s, 19, ACCENT, SANS, 500, spacing=2)


def footer(i: int, total: int, label: str) -> str:
    return "".join([
        L(96, 664, W - 96, 664),
        T(96, 690, label, 14, INK2, SANS, 400, opacity=0.75),
        T(W - 96, 690, f"{i:02d} / {total:02d}", 14, INK2, SANS, 400, anchor="end",
          opacity=0.75),
    ])


# ---------------------------------------------------------------- layouts
def lay_cover(p, meta, ctx) -> list[str]:
    e = [R(0, 0, W, H, PAPER)]
    ix = 760
    e.append(IMG(p["image"], ix, 0, W - ix, H))
    e.append(R(ix, 0, 6, H, PAPER))
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    e.append(L(96, 96, 196, 96, ACCENT, 3))
    t = p["title"]
    size, lines = fit(t, 62, 600, 3)
    y = 300 - (len(lines) - 1) * size * 0.6
    for ln in lines:
        e.append(T(96, y, ln, size, INK, SERIF, 700))
        y += size * 1.16
    e.append(L(96, y + 6, 316, y + 6, ACCENT, 3))
    sub = p.get("subtitle") or meta.get("subtitle", "")
    if sub:
        e.append(T(96, y + 66, sub, 22, INK2, SANS, 400))
    e.append(T(96, 640, meta["meta"], 16, INK2, SANS, 400, opacity=0.8))
    return e


def lay_section(p, meta, ctx) -> list[str]:
    e = [R(0, 0, W, H, DARK)]
    if p.get("image"):
        e.append(IMG(p["image"], 0, 0, W, H))
        e.append(R(0, 0, W, H, "#0B1416", 0.62))
    e.append(T(96, 200, p.get("num", ""), 132, ACCENT, SERIF, 700))
    size, lines = fit(p["title"], 56, 900, 2)
    y = 330
    for ln in lines:
        e.append(T(96, y, ln, size, "#F7F3EC", SERIF, 700))
        y += size * 1.2
    e.append(L(96, y + 10, 216, y + 10, "#F7F3EC", 3, 0.9))
    if p.get("subtitle"):
        e.append(T(96, y + 70, p["subtitle"], 22, "#F7F3EC", SANS, 400, opacity=0.82))
    return e


def lay_statement(p, meta, ctx) -> list[str]:
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    e.append(L(96, 96, 196, 96, ACCENT, 3))
    lines_in = p.get("lines") or [p["title"]]
    y = 260 if len(lines_in) <= 2 else 230
    for ln in lines_in:
        size, ls = fit(ln, 54, W - 260, 2)
        for s in ls:
            e.append(T(96, y, s, size, INK, SERIF, 700))
            y += size * 1.18
        y += 12
    e.append(L(96, y + 10, 356, y + 10, RULE, 2))
    if p.get("note"):
        e.append(T(96, y + 62, p["note"], 22, INK2, SANS, 400))
    if p.get("image"):
        e.append(IMG(p["image"], 900, 430, 300, 190))
    return e


def lay_bullets(p, meta, ctx) -> list[str]:
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    size, tl = fit(p["title"], 40, 700 if p.get("image") else 1000, 2)
    y = 168
    for ln in tl:
        e.append(T(96, y, ln, size, INK, SERIF, 700))
        y += size * 1.12
    e.append(L(96, y + 8, W - 96, y + 8, RULE, 1.5))
    y += 56
    col_w = 700 if p.get("image") else 1000
    for i, b in enumerate(p["bullets"], 1):
        e.append(T(96, y, f"{i:02d}", 20, ACCENT, SANS, 500))
        bs, bl = fit(b, 26, col_w - 70, 2)
        yy = y
        for ln in bl:
            e.append(T(150, yy, ln, bs, INK, SANS, 400))
            yy += bs * 1.35
        y = yy + 22
        if i < len(p["bullets"]):
            e.append(L(150, y - 16, 96 + col_w, y - 16, RULE, 0.8))
    if p.get("image"):
        e.append(IMG(p["image"], 880, 190, 304, 380))
        if p.get("caption"):
            e.append(T(880, 600, p["caption"], 15, INK2, SANS, 400, opacity=0.85))
    return e


def lay_table(p, meta, ctx) -> list[str]:
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    size, tl = fit(p["title"], 38, 1000, 2)
    y = 164
    for ln in tl:
        e.append(T(96, y, ln, size, INK, SERIF, 700))
        y += size * 1.12
    rows = p["table"]
    ncol = max(len(r) for r in rows)
    left, right = 96, W - 96
    tw = right - left
    cw = tw / ncol
    y += 26
    e.append(L(left, y, right, y, INK, 2))
    y += 34
    for ri, row in enumerate(rows):
        hrow = 54
        for ci in range(ncol):
            val = row[ci] if ci < len(row) else ""
            fs = 21 if ri else 20
            fill = INK if ri else ACCENT
            weight = 400 if ri else 500
            e.append(T(left + ci * cw + 8, y, val, fs, fill, SANS, weight))
        y += hrow
        e.append(L(left, y - 22, right, y - 22, RULE, 0.8))
    if p.get("caption"):
        e.append(T(96, y + 18, p["caption"], 16, INK2, SANS, 400, opacity=0.85))
    return e


def lay_compare(p, meta, ctx) -> list[str]:
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    size, tl = fit(p["title"], 38, 1000, 2)
    y = 160
    for ln in tl:
        e.append(T(96, y, ln, size, INK, SERIF, 700))
        y += size * 1.12
    y += 40
    cols = p["cols"]
    cw = (W - 192) / len(cols)
    e.append(L(W // 2, y - 10, W // 2, y + 260, RULE, 1.5))
    for ci, c in enumerate(cols):
        x = 96 + ci * cw
        e.append(T(x, y, c["label"], 22, ACCENT if ci == 0 else TEAL, SANS, 500))
        e.append(T(x, y + 62, c["head"], 34, INK, SERIF, 700))
        yy = y + 108
        for b in c.get("bullets", []):
            for ln in wrap(b, 19, cw - 60)[:2]:
                e.append(T(x, yy, ln, 19, INK2, SANS, 400))
                yy += 28
            yy += 6
    return e


def lay_image_full(p, meta, ctx) -> list[str]:
    e = [R(0, 0, W, H, PAPER), IMG(p["image"], 0, 0, W, H)]
    e.append(R(0, 300, W, H - 300, DARK, 0.55))
    e.append(T(96, 430, p.get("kicker", ""), 18, "#F7F3EC", SANS, 500,
               spacing=2, opacity=0.9))
    size, lines = fit(p["title"], 52, 1000, 2)
    y = 500
    for ln in lines:
        e.append(T(96, y, ln, size, "#F7F3EC", SERIF, 700))
        y += size * 1.15
    if p.get("caption"):
        e.append(T(W - 96, 690, p["caption"], 15, "#F7F3EC", SANS, 400, anchor="end",
                   opacity=0.8))
    return e


def _axes(e, x0=190, y0=590, x1=1080, y1=210):
    e.append(L(x0, y1 - 20, x0, y0, INK, 1.5))
    e.append(L(x0, y0, x1, y0, INK, 1.5))


def lay_chart(p, meta, ctx) -> list[str]:
    """曲线图：p['series'] = [{'name','peak','color','dash'}]，p['x']/p['y'] 轴标签。"""
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    size, tl = fit(p["title"], 36, 620, 2)
    y = 160
    for ln in tl:
        e.append(T(96, y, ln, size, INK, SERIF, 700))
        y += size * 1.12
    X0, Y0, X1, Y1 = 200, 580, 760, 250
    e.append(L(X0, Y1 - 30, X0, Y0, INK, 1.5))
    e.append(L(X0, Y0, X1, Y0, INK, 1.5))
    e.append(T(X0 - 16, Y1 - 40, p.get("ylabel", ""), 17, INK2, SANS, 400, anchor="end"))
    e.append(T(X1, Y0 + 34, p.get("xlabel", ""), 17, INK2, SANS, 400, anchor="end"))

    def path_for(peak: float, baseline: float = 1.0, wobble=0.0, cutoff=None) -> str:
        pts = []
        for i in range(81):
            t = i / 80
            if cutoff is not None and t > cutoff:
                v = 0.04
            else:
                u = min(t / 0.55, 1.0)
                v = baseline + (peak - baseline) * (u ** 1.7)
                if t > 0.55:
                    v = baseline + (peak - baseline) * (1 - (t - 0.55) * 0.15)
            pts.append((X0 + 12 + t * (X1 - X0 - 24), Y0 - 20 - (v - 0.04) * (Y0 - Y1 - 20)))
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        return d

    for s in p["series"]:
        dash = ' stroke-dasharray="8 6"' if s.get("dash") else ""
        e.append(f'<path d="{path_for(s["peak"], s.get("baseline", 0.16), cutoff=s.get("cutoff"))}" '
                 f'fill="none" stroke="{s["color"]}" stroke-width="3"{dash} '
                 f'stroke-linecap="round"/>')
    # 图例
    ly = 300
    for s in p["series"]:
        dash = ' stroke-dasharray="8 6"' if s.get("dash") else ""
        e.append(f'<line x1="830" y1="{ly}" x2="880" y2="{ly}" stroke="{s["color"]}" '
                 f'stroke-width="3"{dash}/>')
        e.append(T(892, ly + 7, s["name"], 19, INK, SANS, 400))
        ly += 46
    if p.get("note"):
        yy = ly + 20
        for raw in p["note"].split("\n"):
            for ln in wrap(raw, 17, 400):
                e.append(T(830, yy, ln, 17, INK2, SANS, 400))
                yy += 27
    return e


def lay_checklist(p, meta, ctx) -> list[str]:
    e = [R(0, 0, W, H, PAPER)]
    e.append(kicker(p.get("kicker") or meta["kicker"]))
    size, tl = fit(p["title"], 38, 1000, 2)
    y = 160
    for ln in tl:
        e.append(T(96, y, ln, size, INK, SERIF, 700))
        y += size * 1.12
    y += 44
    for item in p["pairs"]:
        e.append(T(96, y, "✗", 26, ACCENT, SANS, 700))
        for ln in wrap(item["wrong"], 22, 430)[:2]:
            e.append(T(136, y, ln, 22, INK2, SANS, 400))
            y += 30
        e.append(T(600, y - 30, "→", 24, TEAL, SANS, 700))
        yy = y - 30
        for ln in wrap(item["right"], 22, 540)[:2]:
            e.append(T(646, yy, ln, 22, INK, SANS, 500))
            yy += 30
        y = max(y, yy) + 26
        e.append(L(96, y - 16, W - 96, y - 16, RULE, 0.8))
    return e


def lay_quote(p, meta, ctx) -> list[str]:
    e = [R(0, 0, W, H, PAPER if not p.get("image") else DARK)]
    if p.get("image"):
        e.append(IMG(p["image"], 560, 0, W - 560, H))
        e.append(R(560, 0, 8, H, PAPER))
    e.append(kicker(p.get("kicker") or meta["kicker"], 96, 120))
    lines_in = p.get("lines") or [p["title"]]
    y = 300
    for ln in lines_in:
        size, ls = fit(ln, 50, 460 if p.get("image") else 980, 2)
        for s in ls:
            e.append(T(96, y, s, size, INK, SERIF, 700))
            y += size * 1.22
        y += 16
    e.append(L(96, y + 20, 276, y + 20, ACCENT, 3))
    if p.get("note"):
        e.append(T(96, y + 76, p["note"], 19, INK2, SANS, 400))
    return e


LAYOUTS = {
    "cover": lay_cover, "section": lay_section, "statement": lay_statement,
    "bullets": lay_bullets, "table": lay_table, "compare": lay_compare,
    "image": lay_image_full, "chart": lay_chart, "checklist": lay_checklist,
    "quote": lay_quote,
}


# ---------------------------------------------------------------- parse md
def parse_md(path: Path) -> tuple[dict, list[dict]]:
    t = path.read_text(encoding="utf-8")
    lines = t.splitlines()
    meta = {"title": "", "subtitle": "", "kicker": "", "meta": ""}
    slides: list[dict] = []
    cur = None
    for ln in lines:
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
            cur = {"num": m.group(1), "title": m.group(2).strip(), "bullets": [],
                   "table": [], "note": ""}
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


def choose_layout(s: dict, spec: dict) -> str:
    if spec.get("layout"):
        return spec["layout"]
    if s["table"]:
        return "table"
    if len(s["bullets"]) <= 2:
        return "statement"
    return "bullets"


def build(md: Path, plan: Path, out: Path, images: Path, skill: Path,
          title: str | None) -> Path:
    meta, slides = parse_md(md)
    p = json.loads(plan.read_text(encoding="utf-8")) if plan.exists() else {"pages": []}
    specs = p.get("pages", [])
    meta["kicker"] = p.get("kicker", meta.get("kicker") or meta["title"])
    meta["meta"] = p.get("meta", "")
    if title:
        meta["title"] = title

    out.mkdir(parents=True, exist_ok=True)
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
        page.setdefault("bullets", s["bullets"])
        if not page.get("table") and s["table"]:
            page["table"] = s["table"]
        lay = choose_layout(s, spec)
        body = LAYOUTS[lay](page, meta, {"i": i, "total": total})
        if lay not in ("cover", "section", "image", "quote"):
            body.append(footer(i, total, meta["title"]))

        # 背景作为根图元（PPT Master 要求：静态页面框架声明 data-pptx-role）
        bg, rest = None, body
        if body and ('width="1280" height="720"' in body[0] or
                     'width="1280" height="720"' in body[0] or
                     ('width="1280"' in body[0] and 'height="720"' in body[0]) or
                     ('width="640"' in body[0] and 'height="720"' in body[0])):
            bg, rest = body[0], body[1:]
        if bg is not None:
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

    # 讲稿备注：PPT Master 读 notes/total.md（# NN_标题 分页，--- 分隔）
    notes_dir = out / "notes"
    notes_dir.mkdir(exist_ok=True)
    blocks = [f"# {i:02d}_{s['title']}\n\n{(s.get('note') or '')}" for i, s in enumerate(slides, 1)]
    (notes_dir / "total.md").write_text("\n\n---\n\n".join(blocks) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, str(skill / "scripts/total_md_split.py"), str(out)],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 规范化为 PPT Master 的 compact authoring 写法（官方 normalizer）
    subprocess.run([sys.executable, str(skill / "scripts/compact_svg_styles.py"),
                    str(svgdir), "--inplace"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 交付前自检 + 导出（PPT Master 官方通道）
    subprocess.run([sys.executable, str(skill / "scripts/svg_quality_checker.py"),
                    str(out), "--quick-generate", "--canonical-authoring",
                    "--stage", "final", "--json"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pptx = out / (md.stem + ".pptx")
    r = subprocess.run([sys.executable, str(skill / "scripts/svg_to_pptx.py"),
                        str(out), "--quick-generate", "--primary-language", "zh-CN",
                        "--with-notes", "-o", str(pptx)],
                       capture_output=True, text=True)
    print(r.stdout[-1500:] if r.stdout else "")
    if r.returncode != 0:
        print(r.stderr[-1500:], file=sys.stderr)
        sys.exit(r.returncode)
    write_preview(out, meta, total)
    return pptx



PREVIEW = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{title} · 版式预览</title>
<style>
:root{{--paper:#F7F3EC;--ink:#16262A;--accent:#C2542F}}
body{{margin:0;background:#0d1416;color:#e8e2d6;font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif}}
header{{padding:28px 40px 8px}} h1{{font-size:20px;margin:0 0 6px;font-weight:600}}
p.meta{{margin:0;color:#8fa0a3;font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(460px,1fr));gap:22px;padding:24px 40px 60px}}
figure{{margin:0;background:#16262a;border-radius:6px;overflow:hidden}}
img{{width:100%;display:block;background:var(--paper)}}
figcaption{{font-size:12px;color:#8fa0a3;padding:8px 10px}}
</style></head><body>
<header><h1>{title}</h1><p class="meta">{meta} · 共 {total} 页 · 由 PPT Master 通道导出（文字/图片/曲线均为原生对象）</p></header>
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
    ap.add_argument("--title", default=None)
    a = ap.parse_args()
    pptx = build(Path(a.md), Path(a.plan) if a.plan else Path(a.md).with_suffix(".plan.json"),
                 Path(a.out), Path(a.images), Path(a.skill), a.title)
    print(f"[ok] {pptx}")


if __name__ == "__main__":
    main()
