#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ocr_layout.py — 复刻模式工具链：把参考帖的版式"读"出来，再验收合成页。

对参考图跑中文 OCR，自动分出三类文字区并逐像素量出版式常量：
  - 顶部标签区（title：y 中心 < 12% 且水平居中）
  - 中幅点题句区（reveal：y 中心 50–66% 且水平居中）
  - 对白气泡区（bubbles：其余；输出锚点=文字框中心的比例坐标）
同时量出：墨色、字号（框高）、气泡底色/描边/形状充实率、纸纹强度、色板。

用法：
  python ocr_layout.py --refs <目录或逗号分隔文件> [--out layout.json]
  python ocr_layout.py --verify-art <底图.png> [--ref <原图.png>]     # 底图必须无文字
  python ocr_layout.py --verify-page <合成页.png> --spec <spec.json>  # 文案落位验收

依赖（复刻模式专用，compose.py 不需要）：
  pip install rapidocr-onnxruntime numpy opencv-python-headless
"""
import argparse
import glob
import json
import os
import sys

PUNCT = "，。！？…·、；：「」『』（）()【】,.!?~～*＊ "

def norm(s):
    return "".join(ch for ch in s if ch not in PUNCT and not ch.isspace())


def similar(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()

_OCR = None

def get_ocr():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    return _OCR

def ocr_page(path):
    res, _ = get_ocr()(path)
    out = []
    if res:
        for box, text, score in res:
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            out.append({"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
                        "text": text, "score": round(float(score), 2)})
    return out

# ---------- 分类 ----------

def classify(boxes, W, H):
    title, reveal, bubbles = [], [], []
    for b in boxes:
        cx = (b["x0"] + b["x1"]) / 2.0 / W
        cy = (b["y0"] + b["y1"]) / 2.0 / H
        if cy < 0.12 and abs(cx - 0.5) < 0.16:
            title.append(b)
        elif 0.50 <= cy <= 0.66 and abs(cx - 0.5) < 0.13:
            reveal.append(b)
        else:
            bubbles.append(b)
    return title, reveal, bubbles

def merge_group(group):
    group = sorted(group, key=lambda b: (round(b["y0"] / 30.0), b["x0"]))
    return {"x0": min(b["x0"] for b in group), "y0": min(b["y0"] for b in group),
            "x1": max(b["x1"] for b in group), "y1": max(b["y1"] for b in group),
            "text": " ".join(b["text"] for b in group)}

# ---------- 像素测量 ----------

def text_color(arr, box):
    """文字墨色 = 框内暗像素的中位色；coverage = 暗像素占比（估笔画粗细）。"""
    import numpy as np
    import cv2
    crop = arr[int(box["y0"]):int(box["y1"]) + 1, int(box["x0"]):int(box["x1"]) + 1]
    if crop.size == 0:
        return None, 0.0
    g = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    dark = g < 115
    if dark.sum() < 10:
        return None, 0.0
    return [int(v) for v in np.median(crop[dark], axis=0)], round(float(dark.mean()), 3)

def bubble_style(arr, box, pad=30):
    """气泡样式：底色、描边色/宽、形状充实率（椭圆≈0.79，圆角矩形≥0.88）。"""
    import numpy as np
    import cv2
    H, W = arr.shape[:2]
    x0 = max(0, int(box["x0"]) - pad)
    y0 = max(0, int(box["y0"]) - pad)
    x1 = min(W, int(box["x1"]) + pad)
    y1 = min(H, int(box["y1"]) + pad)
    if x1 - x0 < 24 or y1 - y0 < 24:
        return None
    crop = arr[y0:y1, x0:x1]
    g = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    white = (g > 205).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(white, 8)
    if n <= 1:
        return None
    comp = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    bx, by, bw, bh, area = [int(v) for v in stats[comp]]
    if area < 400 or bw < 30 or bh < 20:
        return None
    mask = (lab == comp)
    fill = [int(v) for v in np.median(crop[mask], axis=0)]
    fill_ratio = round(area / float(bw * bh), 3)
    dil = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=7)
    ring = dil.astype(bool) & ~mask & (g < 150)
    outline = [int(v) for v in np.median(crop[ring], axis=0)] if ring.sum() > 30 else None
    er = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8))
    boundary = mask & ~er.astype(bool)
    per = max(1, int(boundary.sum()))
    outline_w = int(round(float(ring.sum()) / per)) if ring.sum() > 30 else 0
    return {"fill": fill, "fill_ratio": fill_ratio, "outline": outline,
            "outline_w": outline_w}

def grain_metric(arr):
    """纸纹强度：平涂区的高频残差标准差。"""
    import numpy as np
    import cv2
    g = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY).astype(np.float32)
    m = cv2.medianBlur(g.astype(np.uint8), 5).astype(np.float32)
    d = g - m
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1)
    flat = (np.abs(gx) + np.abs(gy)) < 20
    if flat.sum() < 1000:
        return 0.0
    return float(np.std(d[flat]))

def palette(img, k=6):
    import numpy as np
    import cv2
    small = img.resize((160, 214))
    arr = np.asarray(small).reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(arr, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=k)
    order = np.argsort(-counts)
    return [{"rgb": [int(v) for v in centers[i]],
             "share": round(float(counts[i]) / len(labels), 3)} for i in order]

# ---------- 测量参考图 ----------

def measure(path):
    from PIL import Image
    import numpy as np
    img = Image.open(path).convert("RGB")
    W, H = img.size
    arr = np.asarray(img)
    boxes = ocr_page(path)
    title, reveal, bubbles = classify(boxes, W, H)
    page = {"file": os.path.basename(path), "size": [W, H]}
    for name, group in (("title", title), ("reveal", reveal)):
        if group:
            m = merge_group(group)
            c, cov = text_color(arr, m)
            page[name] = {
                "box": [int(m["x0"]), int(m["y0"]), int(m["x1"]), int(m["y1"])],
                "text": m["text"],
                "font_px": int(m["y1"] - m["y0"]),
                "center_y": round((m["y0"] + m["y1"]) / 2.0 / H, 3),
                "ink": c, "coverage": cov,
            }
    bl = []
    for b in sorted(bubbles, key=lambda b: b["y0"]):
        bl.append({
            "anchor": [round((b["x0"] + b["x1"]) / 2.0 / W, 3),
                       round((b["y0"] + b["y1"]) / 2.0 / H, 3)],
            "box": [int(b["x0"]), int(b["y0"]), int(b["x1"]), int(b["y1"])],
            "text": b["text"],
            "style": bubble_style(arr, b),
        })
    page["bubbles"] = bl
    page["grain"] = round(grain_metric(arr), 2)
    page["palette"] = palette(img)
    return page

# ---------- 验收 ----------

def verify_art(path, ref=None):
    ok = True
    boxes = ocr_page(path)
    bad = [b for b in boxes if b["score"] >= 0.6 and len(norm(b["text"])) >= 2]
    if bad:
        ok = False
        print("  FAIL 残留文字:", [(b["text"], b["score"]) for b in bad])
    else:
        print("  PASS 无文字")
    from PIL import Image
    img = Image.open(path).convert("RGB")
    pal = palette(img)
    print("  主色", pal[0]["rgb"], "份额", pal[0]["share"], "| 纸纹", round(grain_metric(np.asarray(img)), 2) if False else "")
    if ref:
        rimg = Image.open(ref).convert("RGB")
        rpal = palette(rimg)
        d = max(abs(a - b) for a, b in zip(pal[0]["rgb"], rpal[0]["rgb"]))
        print("  对参考主色差(0-255):", d, "->", "PASS" if d < 45 else "WARN")
        import numpy as np
        print("  纸纹 参考", round(grain_metric(np.asarray(rimg)), 2),
              "本图", round(grain_metric(np.asarray(img)), 2))
    return ok

def verify_page(path, spec_path):
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    item = None
    base = os.path.basename(path)
    for it in spec:
        if it.get("out") == base:
            item = it
            break
    if item is None:
        print("  FAIL spec 中找不到", base)
        return False
    from PIL import Image
    W, H = Image.open(path).size
    boxes = ocr_page(path)
    ok = True
    expected = []
    if item.get("label"):
        expected.append(("label", "".join(item["label"]) if isinstance(item["label"], list) else item["label"], None))
    if item.get("reveal"):
        expected.append(("reveal", item["reveal"], None))
    for i, bub in enumerate(item.get("bubbles", [])):
        expected.append(("bubble%d" % i, "".join(bub["lines"]), bub.get("anchor")))
    t = item.get("title")
    if t:
        expected.append(("title", "".join(t) if isinstance(t, list) else t, None))
    if item.get("subtitle"):
        expected.append(("subtitle", item["subtitle"], None))
    for i, part in enumerate(item.get("bubble", []) or []):
        expected.append(("legacy_bubble%d" % i, part, None))
    used = set()
    for role, text, anchor in expected:
        want = norm(text)
        hit = None
        for j, b in enumerate(boxes):
            if j in used:
                continue
            got = norm(b["text"])
            if want in got or got in want:
                hit = (j, b)
                break
            # OCR 形近字误读容忍（于/乎、己/已等）：长度差 ≤2 且相似度 ≥0.8
            if len(got) >= 3 and abs(len(got) - len(want)) <= 2 and similar(want, got) >= 0.8:
                hit = (j, b)
                break
        if hit is None:
            ok = False
            print("  FAIL [%s] 未找到: %s" % (role, text))
            continue
        used.add(hit[0])
        b = hit[1]
        cy = (b["y0"] + b["y1"]) / 2.0 / H
        if role == "label" and not (cy < 0.20):
            ok = False
            print("  FAIL [%s] 位置 y=%.2f 应在顶部" % (role, cy))
        if role == "reveal" and not (0.48 <= cy <= 0.68):
            ok = False
            print("  FAIL [%s] 位置 y=%.2f 应在中幅" % (role, cy))
        if anchor:
            bx = (b["x0"] + b["x1"]) / 2.0 / W
            if abs(bx - anchor[0]) > 0.08 or abs(cy - anchor[1]) > 0.08:
                ok = False
                print("  FAIL [%s] 锚点偏离: 实测(%.2f,%.2f) spec(%.2f,%.2f)"
                      % (role, bx, cy, anchor[0], anchor[1]))
            else:
                print("  PASS [%s] 锚点(%.2f,%.2f)" % (role, bx, cy))
                continue
        print("  PASS [%s] %s @y=%.2f" % (role, text[:14], cy))
    def _fragment_of(got: str, texts: list) -> bool:
        """OCR 把一行拆成多框/形近误读时，剩余片段是某预期文本连续窗口的近似。"""
        for t in texts:
            tn = norm(t)
            if 3 <= len(got) <= len(tn):
                for i in range(len(tn) - len(got) + 1):
                    if similar(got, tn[i:i + len(got)]) >= 0.6:
                        return True
        return False

    exp_texts = [t for _, t, _a in expected]
    for j, b in enumerate(boxes):
        if j not in used and b["score"] >= 0.6 and len(norm(b["text"])) >= 2:
            frag = any(norm(b["text"]) in norm(t) for t in exp_texts)
            if not frag:
                frag = _fragment_of(norm(b["text"]), exp_texts)
            if not frag:
                # 与已匹配框的高度重叠重读也不算多出文字
                for k in used:
                    u = boxes[k]
                    vy = min(b["y1"], u["y1"]) - max(b["y0"], u["y0"])
                    vx = min(b["x1"], u["x1"]) - max(b["x0"], u["x0"])
                    if vy > 0.5 * (b["y1"] - b["y0"]) and vx > 0:
                        frag = True
                        break
            if not frag:
                ok = False
                print("  FAIL 多出文字:", b["text"], "@y=%.2f" % ((b["y0"] + b["y1"]) / 2.0 / H))
    return ok

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs")
    ap.add_argument("--out")
    ap.add_argument("--verify-art")
    ap.add_argument("--verify-page")
    ap.add_argument("--spec")
    ap.add_argument("--ref")
    args = ap.parse_args()
    if args.refs:
        paths = []
        for tok in args.refs.split(","):
            paths += sorted(glob.glob(os.path.join(tok, "*.png"))) + \
                     sorted(glob.glob(os.path.join(tok, "*.jpg"))) if os.path.isdir(tok) else [tok]
        pages = [measure(p) for p in paths]
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(pages, f, ensure_ascii=False, indent=1)
        for p in pages:
            t = p.get("title", {})
            r = p.get("reveal", {})
            print("%s  %dx%d  标签[%s]%dpx cy=%.3f 墨%s 覆%.2f | 点题[%s] cy=%.3f 墨%s | 气泡%d 纸纹%.2f" % (
                p["file"], p["size"][0], p["size"][1],
                t.get("text", "-"), t.get("font_px", 0), t.get("center_y", 0),
                t.get("ink"), t.get("coverage", 0),
                r.get("text", "-"), r.get("center_y", 0), r.get("ink"),
                len(p["bubbles"]), p["grain"]))
        return 0
    if args.verify_art:
        ok = verify_art(args.verify_art, args.ref)
        return 0 if ok else 1
    if args.verify_page:
        ok = verify_page(args.verify_page, args.spec)
        return 0 if ok else 1
    ap.print_help()
    return 2

if __name__ == "__main__":
    sys.exit(main())
