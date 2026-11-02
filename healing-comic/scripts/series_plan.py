#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""series_plan.py — 连载拆解器：把「内容地图」拆成一次 10 张的漫画文案批次。

解决的问题是：一本 13 章 104 条的指南没法一次画完。这个脚本把人工/模型
整理的内容地图（guide-map.md）机械化为：
  1. 每批 ≤10 张（封面 + ≤9 内容页）——对齐图片生成的单轮额度与小红书 18 图上限
  2. 每页文案过 gate：标签 ≤8 字 · 点题句 ≤14 字 · 台词每行 ≤12 字（气泡宽度实测上限）
  3. 气泡锚点自动交替（上拍 y0.15 / 下拍 y0.65，左右 0.22/0.80 随页交替）
  4. 直接产出 compose.py 可用的 spec-seriesNN.json（--layout xhs2）
  5. 汇总 series-plan.md：全书连载总表 + 每批分镜表 + 状态列

内容地图语法（guide-map.md）：
  ## 第01批 主题 | 源: 章节或 Q 范围 | 状态: ready 或 skeleton
  - 封面 | title: 两行用/隔开 | hook: 副题钩子 | scene: 画面
  - 页 | label: 标签 | reveal: 点题句 | trigger: 触发句(/分行) | guide: 引导句(/分行) | scene: 画面 | source: 源文
  skeleton 批次只写 ## 行，不写页；脚本在总表中标「待写文案」。

用法：
  python3 series_plan.py --map references/guide-map.md \
      --plan references/series-plan.md --spec-dir examples/
之后画图：底图放 examples/art-s01/…，跑
  compose.py examples/spec-series01.json --layout xhs2 …
"""
import argparse
import json
import re
import sys
from pathlib import Path

MAX_PAGES = 10          # 每批页数上限（封面 + 内容页）
MAX_LABEL = 8           # 标签字数
MAX_REVEAL = 14         # 点题句字数
MAX_LINE = 12           # 气泡单行字数（66px 标签 34px 台词的实测宽度上限）


def parse_map(path: Path):
    batches, cur = [], None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        m = re.match(r"^##\s*第(\d+)批\s*(.*)", line)
        if m:
            head = m.group(2)
            parts = [p.strip() for p in head.split("|")]
            cur = {"no": int(m.group(1)), "topic": parts[0],
                   "src": next((p.split(":", 1)[1].strip()
                                for p in parts if p.startswith("源:")), ""),
                   "status": "skeleton", "pages": []}
            for p in parts:
                if p.startswith("状态:"):
                    cur["status"] = p[3:].strip()
            batches.append(cur)
            continue
        if line.startswith("- ") and cur is not None:
            fields = {}
            for seg in [s.strip() for s in line[2:].split("|")]:
                if ":" in seg:
                    k, v = seg.split(":", 1)
                    fields[k.strip()] = v.strip()
            if "title" in fields or "label" in fields:
                cur["pages"].append(fields)
    return batches


def cjk_len(s: str) -> int:
    return len(s)


def build_page(page: dict, idx: int):
    """把一页地图条目转成 spec item；返回 (item, 警告列表)。"""
    warns = []
    if "title" in page:  # 封面
        title = [t.strip() for t in page["title"].split("/") if t.strip()]
        item = {"art": None, "layout": "xhs2-cover", "title": title,
                "subtitle": page.get("hook", ""), "out": None}
        if len(title) > 2:
            warns.append("封面标题超过两行")
        return item, warns
    label = page.get("label", "")
    reveal = page.get("reveal", "")
    trig = [t.strip() for t in page.get("trigger", "").split("/") if t.strip()]
    guide = [g.strip() for g in page.get("guide", "").split("/") if g.strip()]
    if cjk_len(label) > MAX_LABEL:
        warns.append(f"标签超 {MAX_LABEL} 字：{label}")
    if cjk_len(reveal) > MAX_REVEAL:
        warns.append(f"点题句超 {MAX_REVEAL} 字：{reveal}")
    for t in trig + guide:
        if cjk_len(t) > MAX_LINE:
            warns.append(f"台词行超 {MAX_LINE} 字：{t}")
    # 锚点：上拍 y0.15，下拍 y0.65；左右随页交替（偶数页 触发L/引导R）
    lx, rx = 0.22, 0.80
    left = lx if idx % 2 == 0 else rx
    right = rx if idx % 2 == 0 else lx
    bubbles = []
    if trig:
        bubbles.append({"lines": trig, "anchor": [left, 0.15]})
    if guide:
        bubbles.append({"lines": guide, "anchor": [right, 0.65]})
    item = {"art": None, "layout": "xhs2", "label": label, "reveal": reveal,
            "bubbles": bubbles, "out": None, "_scene": page.get("scene", ""),
            "_source": page.get("source", "")}
    if not trig and not guide:
        warns.append("本页没有任何台词")
    return item, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--spec-dir", type=Path, default=None)
    a = ap.parse_args()

    batches = parse_map(a.map)
    if not batches:
        sys.exit("内容地图里没解析到任何批次（## 第NN批）")

    a.plan.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 连载计划（series_plan.py 生成）", "",
             f"源地图：`{a.map}` · 每批 ≤{MAX_PAGES} 张（对齐生图单轮额度）", "",
             "| 批 | 主题 | 源 | 页数 | 状态 |", "|---|---|---|---|---|"]
    fail = False
    for b in batches:
        n = len(b["pages"])
        if n > MAX_PAGES:
            print(f"[gate FAIL] 第{b['no']:02d}批 {n} 页超过 {MAX_PAGES} 张")
            fail = True
        status = "✅ 文案就绪" if b["status"] == "ready" else "⬜ 待写文案"
        lines.append(f"| {b['no']:02d} | {b['topic']} | {b['src']} | "
                     f"{n or '—'} | {status} |")

    for b in batches:
        if not b["pages"]:
            continue
        lines += ["", f"## 第{b['no']:02d}批 · {b['topic']}（{b['src']}）",
                  "", "| 页 | 标签 | 点题句 | 触发句 | 引导句 | 画面 | 源文 |",
                  "|---|---|---|---|---|---|---|"]
        items = []
        for i, page in enumerate(b["pages"]):
            item, warns = build_page(page, i)
            for w in warns:
                print(f"[gate FAIL] 第{b['no']:02d}批 第{i}页：{w}")
                fail = True
            items.append(item)
            if "title" in page:
                lines.append(f"| 封面 | {' / '.join(item['title'])} | 钩子：{item['subtitle']} | — | — | "
                             f"{page.get('scene','')} | — |")
            else:
                lines.append(
                    f"| {i} | {page.get('label','')} | {page.get('reveal','')} | "
                    f"{page.get('trigger','').replace('/', ' ')} | "
                    f"{page.get('guide','').replace('/', ' ')} | "
                    f"{page.get('scene','')} | {page.get('source','')} |")
        if a.spec_dir and b["status"] == "ready":
            a.spec_dir.mkdir(parents=True, exist_ok=True)
            art = f"art-s{b['no']:02d}"
            for i, it in enumerate(items, 1):
                it["art"] = f"{art}/00-cover.png" if it["layout"] == "xhs2-cover" else f"{art}/{i:02d}.png"
                it["out"] = f"系列{b['no']:02d}_{i:02d}.png"
                for k in ("_scene", "_source"):
                    it.pop(k, None)
            spec_path = a.spec_dir / f"spec-series{b['no']:02d}.json"
            spec_path.write_text(json.dumps(items, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
            print(f"[spec] {spec_path}")

    lines += ["", "## 使用", "",
              "```sh",
              "python3 scripts/compose.py examples/spec-series01.json --layout xhs2 \\",
              "  --font <Regular.ttf> --font-medium <Medium.ttf> \\",
              "  --art-root examples --outdir examples/pages-s01 --html --contact-sheet",
              "python3 scripts/ocr_layout.py --verify-page examples/pages-s01/系列01_02.png \\",
              "  --spec examples/spec-series01.json",
              "```",
              "", "底图放 `examples/art-sNN/`（00-cover + 01…），逐页画 `分镜表` 的画面列。"]
    a.plan.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[plan] {a.plan}")
    if fail:
        sys.exit("[gate FAIL] 文案有超限项，修 guide-map.md 后重跑")
    print("[gate] all pass")


if __name__ == "__main__":
    main()
