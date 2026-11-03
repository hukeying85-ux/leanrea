#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给原生 pptx 加"按块出现"的进场动画（淡入 0.5s）。

为什么单独做一个后处理：
    PPT Master 的 SVG→PPTX 只出静态页，python-pptx 也不支持动画。
    但动画在 OOXML 里就是 `ppt/slides/slideN.xml` 末尾的一段 `<p:timing>`，
    引用形状 id（spTgt spid）即可——所以可以直接改包。

做法（不改变任何排版坐标）：
    1. 读出每页 content 组里的形状，按纵向区间做"行带"合并（重叠即同带）；
    2. 每个行带包成一个新的子组（子组的 xfrm/chOff 与原组完全一致，
       所以坐标不变，只是多了一层可被动画引用的对象）；
    3. 第一带（通常是满版底图 + 标题）随页面自动出现，其余每带一次点击淡入；
    4. 页脚带并进最后一带，避免"点一下才出现页码"。

用法：
    python3 scripts/animate_pptx.py in.pptx out.pptx [--dry-run]
"""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

from lxml import etree

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"p": P, "a": A}
EMU = 9525.0          # 1px @96dpi
W_PX, H_PX = 1280, 720


def q(tag: str) -> str:
    pre, name = tag.split(":")
    return f"{{{P if pre == 'p' else A}}}{name}"


def shape_box(el):
    off = el.find(".//a:xfrm/a:off", NS)
    ext = el.find(".//a:xfrm/a:ext", NS)
    if off is None or ext is None:
        return None
    x = int(off.get("x", 0)) / EMU
    y = int(off.get("y", 0)) / EMU
    w = int(ext.get("cx", 0)) / EMU
    h = int(ext.get("cy", 0)) / EMU
    return x, y, w, h


def clusters(shapes, gap=24.0, min_h=22.0):
    """按**文档顺序**分块（SVG 的绘制顺序 = 阅读顺序）。

    · 满版底图/底色（≈整页）单独作为第一块，随页面自动出现；
    · 之后的形状依次归并：只有比当前块底部低出一截（> gap）才另起一块；
    · 后出现的图形若位置更靠上（如图文对开页的插图），归回当前块。
    """
    bg, out, cur = [], [], None
    for el in shapes:
        box = shape_box(el)
        if not box:
            continue
        _x, y, w, h = box
        if w >= 0.92 * W_PX and h >= 0.88 * H_PX:
            bg.append(el)
            continue
        if cur is not None and y <= cur["bottom"] + gap:
            cur["els"].append(el)
            cur["bottom"] = max(cur["bottom"], y + h)
        else:
            cur = {"top": y, "bottom": y + h, "els": [el]}
            out.append(cur)
    # 太薄的一块（kicker、分隔线、单条网格线）并进邻块，避免"点一下才出一个小点"
    thin = []
    for b in out:
        if thin and (thin[-1]["bottom"] - thin[-1]["top"]) < min_h:
            thin[-1]["els"] += b["els"]
            thin[-1]["bottom"] = max(thin[-1]["bottom"], b["bottom"])
        else:
            thin.append(b)
    if len(thin) > 1 and (thin[-1]["bottom"] - thin[-1]["top"]) < min_h:
        thin[-2]["els"] += thin[-1]["els"]
        thin[-2]["bottom"] = max(thin[-2]["bottom"], thin[-1]["bottom"])
        thin.pop()
    if bg:
        thin.insert(0, {"top": 0, "bottom": H_PX, "els": bg, "bg": True})
    return thin


def max_id(root) -> int:
    ids = [int(e.get("id")) for e in root.iter(q("p:cNvPr")) if e.get("id", "").isdigit()]
    return max(ids) if ids else 1


def make_group(nid: int, name: str, children) -> etree._Element:
    g = etree.Element(q("p:grpSp"))
    nv = etree.SubElement(g, q("p:nvGrpSpPr"))
    cnv = etree.SubElement(nv, q("p:cNvPr"))
    cnv.set("id", str(nid))
    cnv.set("name", name)
    etree.SubElement(nv, q("p:cNvGrpSpPr"))
    etree.SubElement(nv, q("p:nvPr"))
    pr = etree.SubElement(g, q("p:grpSpPr"))
    xfrm = etree.SubElement(pr, q("a:xfrm"))
    for tag, x, y, cx, cy in (("a:off", 0, 0, None, None), ("a:ext", None, None, W_PX * EMU, H_PX * EMU),
                              ("a:chOff", 0, 0, None, None), ("a:chExt", None, None, W_PX * EMU, H_PX * EMU)):
        e = etree.SubElement(xfrm, q(tag))
        if x is not None:
            e.set("x", str(int(x)))
            e.set("y", str(int(y)))
        else:
            e.set("cx", str(int(cx)))
            e.set("cy", str(int(cy)))
    for ch in children:
        g.append(ch)          # move（lxml 会自动从父节点摘除）
    return g


def timing_xml(steps) -> etree._Element:
    """steps: [(spid, mode)]，mode = auto / click。"""
    nid = [100]
    def nxt():
        nid[0] += 1
        return nid[0]

    timing = etree.Element(q("p:timing"), nsmap={"p": P, "a": A})
    tnLst = etree.SubElement(timing, q("p:tnLst"))
    root_par = etree.SubElement(tnLst, q("p:par"))
    ctn = etree.SubElement(root_par, q("p:cTn"))
    ctn.set("id", str(nxt()))
    ctn.set("dur", "indefinite")
    ctn.set("restart", "never")
    ctn.set("nodeType", "tmRoot")
    child = etree.SubElement(ctn, q("p:childTnLst"))

    seq = etree.SubElement(child, q("p:seq"))
    seq.set("concurrent", "1")
    seq.set("nextAc", "seek")
    sctn = etree.SubElement(seq, q("p:cTn"))
    sctn.set("id", str(nxt()))
    sctn.set("dur", "indefinite")
    sctn.set("nodeType", "mainSeq")
    scl = etree.SubElement(sctn, q("p:childTnLst"))

    for spid, mode in steps:
        par = etree.SubElement(scl, q("p:par"))
        c1 = etree.SubElement(par, q("p:cTn"))
        c1.set("id", str(nxt()))
        c1.set("fill", "hold")
        st = etree.SubElement(c1, q("p:stCondLst"))
        cond = etree.SubElement(st, q("p:cond"))
        cond.set("delay", "0" if mode == "auto" else "indefinite")
        c1l = etree.SubElement(c1, q("p:childTnLst"))

        p2 = etree.SubElement(c1l, q("p:par"))
        c2 = etree.SubElement(p2, q("p:cTn"))
        c2.set("id", str(nxt()))
        c2.set("fill", "hold")
        st2 = etree.SubElement(c2, q("p:stCondLst"))
        etree.SubElement(st2, q("p:cond")).set("delay", "0")
        c2l = etree.SubElement(c2, q("p:childTnLst"))

        p3 = etree.SubElement(c2l, q("p:par"))
        c3 = etree.SubElement(p3, q("p:cTn"))
        c3.set("id", str(nxt()))
        c3.set("presetID", "10")
        c3.set("presetClass", "entr")
        c3.set("presetSubtype", "0")
        c3.set("fill", "hold")
        c3.set("nodeType", "afterEffect" if mode == "auto" else "clickEffect")
        st3 = etree.SubElement(c3, q("p:stCondLst"))
        etree.SubElement(st3, q("p:cond")).set("delay", "0")
        c3l = etree.SubElement(c3, q("p:childTnLst"))

        # set visibility
        setEl = etree.SubElement(c3l, q("p:set"))
        bhvr = etree.SubElement(setEl, q("p:cBhvr"))
        t = etree.SubElement(bhvr, q("p:cTn"))
        t.set("id", str(nxt()))
        t.set("dur", "1")
        t.set("fill", "hold")
        stc = etree.SubElement(t, q("p:stCondLst"))
        etree.SubElement(stc, q("p:cond")).set("delay", "0")
        tgt = etree.SubElement(bhvr, q("p:tgtEl"))
        etree.SubElement(tgt, q("p:spTgt")).set("spid", str(spid))
        names = etree.SubElement(bhvr, q("p:attrNameLst"))
        etree.SubElement(names, q("p:attrName")).text = "style.visibility"
        to = etree.SubElement(setEl, q("p:to"))
        etree.SubElement(to, q("p:strVal")).set("val", "visible")

        # fade in
        eff = etree.SubElement(c3l, q("p:animEffect"))
        eff.set("transition", "in")
        eff.set("filter", "fade")
        eb = etree.SubElement(eff, q("p:cBhvr"))
        et = etree.SubElement(eb, q("p:cTn"))
        et.set("id", str(nxt()))
        et.set("dur", "500")
        etg = etree.SubElement(eb, q("p:tgtEl"))
        etree.SubElement(etg, q("p:spTgt")).set("spid", str(spid))

    prev = etree.SubElement(seq, q("p:prevCondLst"))
    pc = etree.SubElement(prev, q("p:cond"))
    pc.set("evt", "onPrev")
    pc.set("delay", "0")
    etree.SubElement(etree.SubElement(pc, q("p:tgtEl")), q("p:sldTgt"))
    nxtc = etree.SubElement(seq, q("p:nextCondLst"))
    nc = etree.SubElement(nxtc, q("p:cond"))
    nc.set("evt", "onNext")
    nc.set("delay", "0")
    etree.SubElement(etree.SubElement(nc, q("p:tgtEl")), q("p:sldTgt"))
    return timing


def process_slide(xml_bytes: bytes, idx=0, total=0, verbose=False):
    root = etree.fromstring(xml_bytes)
    tree = root.find(".//p:spTree", NS)
    if tree is None:
        return xml_bytes, []

    # content 组（导出器把整页内容包在一个 <p:grpSp name="content"> 里）
    grp = None
    for g in tree.findall("p:grpSp", NS):
        nv = g.find("p:nvGrpSpPr/p:cNvPr", NS)
        if nv is not None and nv.get("name") in ("content", None, ""):
            grp = g
            break
    container = grp if grp is not None else tree
    shapes = [el for el in container if el.tag in (q("p:sp"), q("p:pic"), q("p:grpSp"))]
    if len(shapes) < 2:
        return xml_bytes, []

    bs = clusters(shapes)
    # 页脚并进上一块（不要"点一下才出现页码"）
    if len(bs) >= 2 and bs[-1]["top"] > 640:
        bs[-2]["els"] += bs[-1]["els"]
        bs.pop()
    while len(bs) > 6:                    # 一步最多六块，多了合并最短的相邻块
        i = min(range(len(bs) - 1), key=lambda k: (bs[k]["bottom"] - bs[k]["top"], k))
        bs[i]["els"] += bs[i + 1]["els"]
        bs[i]["bottom"] = max(bs[i]["bottom"], bs[i + 1]["bottom"])
        bs.pop(i + 1)

    nid = max_id(root)
    groups = []
    for i, b in enumerate(bs):
        nid += 1
        groups.append(make_group(nid, f"step{i + 1}", b["els"]))
    for g in groups:
        container.append(g)
    # 首块（标题/底图）自动出现；封面与收尾页全部自动
    auto_n = 1
    if bs and bs[0].get("bg"):
        auto_n = 2
    if idx in (1, total):                 # 封面与收尾页整体淡入，不需要点
        auto_n = len(bs)
    steps = [(int(g.find("p:nvGrpSpPr/p:cNvPr", NS).get("id")),
              "auto" if i < auto_n else "click") for i, g in enumerate(groups)]

    old = root.find("p:timing", NS)
    if old is not None:
        root.remove(old)
    root.append(timing_xml(steps))
    if verbose:
        n_click = sum(1 for _s, m in steps if m == "click")
        print(f"    {len(bs)} 块 / {len(shapes)} 形状 → {len(bs) - n_click} 自动 + {n_click} 次点击")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), steps


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    src, dst = Path(a.src), Path(a.dst)
    if a.dry_run:
        dst = Path("/tmp/_anim_dry.pptx")
    with zipfile.ZipFile(src) as zin:
        items = [(i, zin.read(i.filename)) for i in zin.infolist()]

    import re as _re
    slides = [i.filename for i, _ in items
              if i.filename.startswith("ppt/slides/slide") and i.filename.endswith(".xml")]
    total_slides = len(slides)
    total = 0
    out = []
    for info, data in items:
        if info.filename.startswith("ppt/slides/slide") and info.filename.endswith(".xml"):
            idx = int(_re.search(r"slide(\d+)\.xml$", info.filename).group(1))
            new, steps = process_slide(data, idx, total_slides, verbose=True)
            total += len(steps)
            data = new
        out.append((info, data))

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, data in out:
            zout.writestr(info, data)
    print(f"[ok] {dst}  共 {total} 个动画步（含首带自动）")


if __name__ == "__main__":
    main()
