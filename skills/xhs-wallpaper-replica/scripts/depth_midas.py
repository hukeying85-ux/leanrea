#!/usr/bin/env python3
"""
depth_midas.py —— 给壁纸出「深度图」（动态 / 3D 壁纸的地基）

模型：MiDaS v2.1 small（Intel ISL，MIT），66 MB ONNX，CPU 一张 1440×1920 约 0.4 s。
      Lively Wallpaper 的「Depth Wallpaper」、DepthFlow 的默认估深器都是同一类单目深度模型。
      沙箱里 GitHub Release / HuggingFace 都不通，但有仓库把官方 model-small.onnx 直接提交进了 git，
      用 blobs API 就能拿到（见 fetch_model()）。

用法：
  python3 scripts/depth_midas.py --fetch                       # 一次性：把模型拉到 ~/.u2net/midas_v21_small.onnx
  python3 scripts/depth_midas.py IN_DIR --out DEPTH_DIR [--glob "金鱼*.png"]   # IN_DIR 里的图 → DEPTH_DIR/同名.png（8 位灰度，近=亮 远=暗）
        [--model PATH] [--guided 16] [--gamma 1.0] [--preview]  # --preview 另存一张 伪彩对比图 DEPTH_DIR/预览.jpg

深度图约定：0=最远 255=最近（MiDaS 输出的是「逆深度」，正好近大远小，不用再翻转）。
后续 live_wallpaper.py / parallax_web.py 都按这个约定读。
"""
import argparse, glob, os, subprocess, sys
import numpy as np
import cv2

DEFAULT_MODEL = os.path.expanduser("~/.u2net/midas_v21_small.onnx")
# debkbanerji/lego-art-remix 提交了 MiDaS 官方 model-small.onnx（sha 固定）；blobs API 走 api.github.com，沙箱可达
MODEL_BLOB = ("debkbanerji/lego-art-remix", "9fb7546dd483b4b0e08ff57eab9f51139d86ec4e")
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def fetch_model(path=DEFAULT_MODEL):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    repo, sha = MODEL_BLOB
    with open(path, "wb") as f:
        subprocess.run(["gh", "api", f"repos/{repo}/git/blobs/{sha}", "-H", "Accept: application/vnd.github.raw"],
                       stdout=f, check=True)
    print("[fetch]", path, os.path.getsize(path) // 1024 // 1024, "MB")


def guided_filter(guide, src, r=16, eps=1e-3):
    """He et al. 导向滤波：让 256×256 放大出来的深度贴回原图的边缘（水果轮廓 / 鱼缸边）。"""
    guide = guide.astype(np.float32); src = src.astype(np.float32)
    k = (2 * r + 1, 2 * r + 1)
    mean_i = cv2.blur(guide, k); mean_p = cv2.blur(src, k)
    corr_i = cv2.blur(guide * guide, k); corr_ip = cv2.blur(guide * src, k)
    var_i = corr_i - mean_i * mean_i; cov_ip = corr_ip - mean_i * mean_p
    a = cov_ip / (var_i + eps); b = mean_p - a * mean_i
    return cv2.blur(a, k) * guide + cv2.blur(b, k)


def estimate(sess, bgr, guided=16, gamma=1.0):
    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    x = cv2.resize(rgb, (256, 256), interpolation=cv2.INTER_AREA)
    x = ((x - MEAN) / STD).transpose(2, 0, 1)[None]
    inv = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]          # 逆深度，越大越近
    inv = cv2.resize(inv, (w, h), interpolation=cv2.INTER_CUBIC)
    lo, hi = np.percentile(inv, 1), np.percentile(inv, 99)
    d = np.clip((inv - lo) / max(hi - lo, 1e-6), 0, 1)
    if guided:
        g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        d = np.clip(guided_filter(g, d, r=guided, eps=2e-3), 0, 1)
    if gamma != 1.0:
        d = d ** gamma
    return (d * 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("in_dir", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--guided", type=int, default=16, help="导向滤波半径，0 关闭")
    ap.add_argument("--gamma", type=float, default=1.0, help=">1 压暗远景（加强前后分离），<1 提亮")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--glob", default="*", help='只处理匹配的文件名，如 "金鱼*.png"')
    a = ap.parse_args()
    if a.fetch:
        fetch_model(a.model)
        if not a.in_dir:
            return
    if not a.in_dir or not a.out:
        sys.exit("用法：depth_midas.py IN_DIR --out DEPTH_DIR（或 --fetch）")
    if not os.path.exists(a.model):
        sys.exit(f"模型不存在：{a.model}（先 --fetch）")
    import onnxruntime as ort
    sess = ort.InferenceSession(a.model, providers=["CPUExecutionProvider"])
    os.makedirs(a.out, exist_ok=True)
    files = sorted(f for f in glob.glob(os.path.join(a.in_dir, a.glob)) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
    tiles = []
    for f in files:
        bgr = cv2.imread(f, cv2.IMREAD_COLOR)
        d = estimate(sess, bgr, a.guided, a.gamma)
        name = os.path.splitext(os.path.basename(f))[0]
        cv2.imwrite(os.path.join(a.out, name + ".png"), d)
        print("[depth]", name, d.shape[::-1], "near%:", round(float((d > 170).mean()) * 100, 1))
        if a.preview:
            small = cv2.resize(bgr, (300, 400))
            col = cv2.applyColorMap(cv2.resize(d, small.shape[1::-1]), cv2.COLORMAP_INFERNO)
            tiles.append(np.hstack([small, col]))
    if a.preview and tiles:
        rows = [np.hstack(tiles[i:i + 2]) if i + 1 < len(tiles) else np.hstack([tiles[i], np.zeros_like(tiles[i])])
                for i in range(0, len(tiles), 2)]
        cv2.imwrite(os.path.join(a.out, "预览.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
        print("[preview]", os.path.join(a.out, "预览.jpg"))


if __name__ == "__main__":
    main()
