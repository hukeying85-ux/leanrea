#!/usr/bin/env python3
"""
depth_mask.py —— 给「景深 / 裸眼 3D」壁纸抠前景主体，输出 8-bit 蒙版 PNG（白 = 前景）。

iOS 16+ 锁屏的「景深效果」会把壁纸里的主体放到时钟前面；预览时要模拟这一层，就得先有主体蒙版。
模型：ISNet（@imgly/background-removal-data 里的 models/small|medium，npm registry 可直连，
      GitHub release 资产被沙箱出口拦，HF 也拦）。拼回 onnx：
          python3 scripts/depth_mask.py --assemble ~/.u2net/imgly/package/dist   # 一次性
推理：onnxruntime CPU，1024×1024 输入，每张 2–6 s。

用法：
  python3 scripts/depth_mask.py IN_DIR --out MASK_DIR [--model ~/.u2net/isnet_medium.onnx] [--min-area 0.02]
      IN_DIR 里的 01.png … NN.png → MASK_DIR/NN.png（同尺寸灰度蒙版）+ MASK_DIR/预览.jpg（叠色检查图）
蒙版里前景面积 < min-area（占比）时判为「没有可用主体」，不输出该页蒙版（phone_mockup 会退回普通锁屏叠层）。
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

DEFAULT_MODEL = os.path.expanduser("~/.u2net/isnet_medium.onnx")


def assemble(dist_dir: str, out_dir: str = os.path.expanduser("~/.u2net")):
    r = json.load(open(os.path.join(dist_dir, "resources.json")))
    for name in ("/models/small", "/models/medium"):
        out = os.path.join(out_dir, "isnet_" + name.split("/")[-1] + ".onnx")
        with open(out, "wb") as f:
            for c in r[name]["chunks"]:
                f.write(open(os.path.join(dist_dir, c["hash"]), "rb").read())
        print("[assemble]", out, os.path.getsize(out) // 1024 // 1024, "MB")


def load_session(model: str):
    import onnxruntime as ort  # noqa: WPS433
    so = ort.SessionOptions()
    so.intra_op_num_threads = max(1, os.cpu_count() or 1)
    return ort.InferenceSession(model, so, providers=["CPUExecutionProvider"])


def predict(sess, im: Image.Image) -> np.ndarray:
    """返回 0..1 float 蒙版，尺寸同输入。"""
    w, h = im.size
    x = np.asarray(im.convert("RGB").resize((1024, 1024), Image.BILINEAR), dtype=np.float32) / 255.0
    x = (x - 0.5) / 1.0
    x = x.transpose(2, 0, 1)[None]
    out = sess.run([sess.get_outputs()[0].name], {sess.get_inputs()[0].name: x})[0][0, 0]
    out = (out - out.min()) / max(1e-6, (out.max() - out.min()))
    m = Image.fromarray((out * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
    return np.asarray(m, dtype=np.float32) / 255.0


def clean(mask: np.ndarray, feather: int = 2) -> Image.Image:
    m = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8))
    if feather:
        m = m.filter(ImageFilter.GaussianBlur(feather))
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("in_dir", nargs="?")
    ap.add_argument("--out", default=None)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--min-area", type=float, default=0.02, help="前景占比低于此值视为无主体")
    ap.add_argument("--assemble", default=None, help="@imgly/background-removal-data 的 package/dist 目录，拼出 onnx 后退出")
    a = ap.parse_args()
    if a.assemble:
        assemble(a.assemble)
        return
    if not a.in_dir or not a.out:
        sys.exit("需要 IN_DIR 和 --out")
    if not os.path.exists(a.model):
        sys.exit(f"模型不存在：{a.model}（先 --assemble）")
    sess = load_session(a.model)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in Path(a.in_dir).iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    tiles = []
    for p in files:
        im = Image.open(p).convert("RGB")
        m = predict(sess, im)
        area = float((m > 0.5).mean())
        top = float((m[: m.shape[0] // 3] > 0.5).mean())  # 上 1/3 里的前景占比：决定能不能挡住时钟
        ok = area >= a.min_area
        if ok:
            clean(m).save(out / (p.stem + ".png"))
        print(f"[mask] {p.name}: area={area:.3f} top-third={top:.3f} -> {'ok' if ok else 'skip (no subject)'}")
        # 叠色预览：前景染红
        prev = im.copy()
        prev.thumbnail((360, 800))
        mm = Image.fromarray((m * 255).astype(np.uint8)).resize(prev.size)
        red = Image.new("RGB", prev.size, (255, 40, 40))
        prev = Image.composite(Image.blend(prev, red, 0.55), prev, mm)
        tiles.append(prev)
    if tiles:
        W = sum(t.width for t in tiles) + 10 * (len(tiles) + 1)
        H = max(t.height for t in tiles) + 20
        sheet = Image.new("RGB", (W, H), "white")
        x = 10
        for t in tiles:
            sheet.paste(t, (x, 10))
            x += t.width + 10
        sheet.save(out / "预览.jpg", quality=88)
        print("[sheet]", out / "预览.jpg")


if __name__ == "__main__":
    main()
