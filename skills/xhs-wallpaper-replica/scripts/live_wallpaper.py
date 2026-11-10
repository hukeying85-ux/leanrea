#!/usr/bin/env python3
"""
live_wallpaper.py —— 把一张静态壁纸（+ 深度图）渲染成「无缝循环」的动态壁纸 MP4（可选 GIF 预览、分层 PNG）

纯 CPU：numpy + OpenCV remap + ffmpeg(imageio-ffmpeg 自带二进制)。1440×1920 × 6 s × 30 fps 一支约 20 s。
思路与 depthy / DepthFlow / Lively「Depth Wallpaper」同源：按深度做视差位移（steep parallax 的单层近似），
再叠加几种壁纸常用的「活」效果。所有运动都是周期函数 → 首尾帧天然衔接，手机设成视频壁纸时无缝循环。

模式（--modes 逗号分隔，默认 combo）：
  kenburns   缓慢推拉 + 平移（不需要深度图；最保守，任何图都不会穿帮）
  parallax   深度视差：近景、远景反向轻摆，像手机陀螺仪壁纸；需要 --depth
  layers     两层 3D：按深度阈值抠出近景、背景 inpaint 补洞，前后层不同速移动；同时导出 NN-fg.png(RGBA)/NN-bg.png
             （这两张层图就是 Live Wallpaper Maker / Lively / Wallpaper Engine「分层视差」要的素材）
  particles  漂浮粒子（金色星屑 / 花瓣 / 雪），加法混合，上升 + 闪烁
  shimmer    高光区域的水波流光 + 呼吸辉光（金光柱、水面、星空最吃这个）
  combo      parallax + shimmer + particles 三合一（默认成品）

用法：
  python3 scripts/live_wallpaper.py IMG.png --depth DEPTH.png --out OUT_DIR [--name 金鱼01]
         [--modes combo,parallax] [--seconds 6] [--fps 30] [--size 1080x1440] [--amp 1.0]
         [--particles gold|petal|snow|none] [--highlight lum|sat] [--gif] [--focus 0.45]
输出：OUT_DIR/<name>-<mode>.mp4（H.264 yuv420p，faststart），--gif 另存 480px 宽 15fps 的 GIF。
"""
import argparse, math, os, subprocess, sys
import numpy as np
import cv2

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:  # noqa: BLE001
    FFMPEG = "ffmpeg"

PARTICLE_COLORS = {  # BGR
    "gold": (120, 215, 255),
    "petal": (210, 190, 255),
    "snow": (255, 255, 255),
}


# ---------------------------------------------------------------- 工具
def load_image(path, size=None):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        sys.exit(f"读不到图：{path}")
    if size:
        img = cv2.resize(img, size, interpolation=cv2.INTER_AREA if size[0] < img.shape[1] else cv2.INTER_CUBIC)
    h, w = img.shape[:2]
    if w % 2 or h % 2:  # yuv420p 要偶数边
        img = img[: h - h % 2, : w - w % 2]
    return img


def load_depth(path, shape):
    d = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if d is None:
        sys.exit(f"读不到深度图：{path}")
    d = cv2.resize(d, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255.0
    return cv2.GaussianBlur(d, (0, 0), 3)


class Writer:
    def __init__(self, path, w, h, fps):
        self.path = path
        cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
               "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "fast", "-crf", "19",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", path]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def write(self, frame):
        self.p.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self):
        self.p.stdin.close(); self.p.wait()
        if self.p.returncode:
            sys.exit(f"ffmpeg 失败：{self.path}")


def to_gif(mp4, gif, width=480, fps=15):
    vf = f"fps={fps},scale={width}:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", mp4, "-vf", vf, "-loop", "0", gif], check=True)


def smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- 各种运动
def path_offset(ph, amp_x, amp_y):
    """椭圆摆动：一个周期回到原点 → 无缝。"""
    return amp_x * math.sin(2 * math.pi * ph), amp_y * math.cos(2 * math.pi * ph)


class Scene:
    def __init__(self, img, depth, amp=1.0, focus=0.45, particles="gold", n_particles=140, seed=7, highlight="lum"):
        self.img = img
        self.h, self.w = img.shape[:2]
        self.depth = depth
        self.amp = amp
        self.focus = focus
        # 视差幅度：横向 2.2% 宽，纵向 1.2%
        self.ax = 0.022 * self.w * amp
        self.ay = 0.012 * self.w * amp
        m = int(math.ceil(max(self.ax, self.ay) * 1.1)) + 4
        self.margin = m
        # 预放大一圈做安全边，视差采样永远不出界
        self.big = cv2.resize(img, (self.w + 2 * m, self.h + 2 * m), interpolation=cv2.INTER_CUBIC)
        ys, xs = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        self.base_x = xs + m
        self.base_y = ys + m
        # 高光蒙版（流光 / 辉光用）
        lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        hl = smoothstep(lum, 0.55, 0.92)
        if highlight == "sat":  # 白纸底的画：只让「有颜色的亮部」流光，别让整张白纸呼吸
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
            hl = hl * smoothstep(hsv[..., 1] / 255.0, 0.12, 0.35)
        self.highlight = cv2.GaussianBlur(hl, (0, 0), 6)
        # 粒子
        rng = np.random.default_rng(seed)
        self.pcolor = PARTICLE_COLORS.get(particles)
        n = n_particles if self.pcolor else 0
        self.px = rng.uniform(0, self.w, n)
        self.py = rng.uniform(0, self.h, n)
        self.pk = rng.integers(1, 3, n)                 # 一个周期上升 k 屏高
        self.pr = rng.uniform(1.5, 5.5, n)              # 半径（在 1/2 分辨率层上）
        self.pph = rng.uniform(0, 1, n)                 # 闪烁相位
        self.pn = rng.integers(2, 6, n)                 # 闪烁次数 / 周期
        self.pwig = rng.uniform(6, 22, n)               # 横向摆幅
        self.pwm = rng.integers(1, 4, n)                # 摆动次数 / 周期
        if depth is not None:
            self.pdepth = self.depth[np.clip(self.py.astype(int), 0, self.h - 1), np.clip(self.px.astype(int), 0, self.w - 1)]
        else:
            self.pdepth = np.full(n, 0.6, np.float32)
        self._layers = None

    # --- 视差（单层）
    def parallax_maps(self, ph, strength=1.0):
        ox, oy = path_offset(ph, self.ax * strength, self.ay * strength)
        dd = self.depth - self.focus
        return self.base_x + dd * ox, self.base_y + dd * oy

    def warp(self, map_x, map_y):
        return cv2.remap(self.big, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

    # --- 流光：高光区域的小幅周期位移
    def shimmer_maps(self, ph, map_x, map_y, px_amp=None):
        a = (px_amp or 0.0045 * self.w) * self.amp
        ys, xs = self.base_y, self.base_x
        lam = 0.11 * self.h
        dx = a * np.sin(2 * math.pi * (ys / lam + ph * 2)) * self.highlight
        dy = 0.6 * a * np.cos(2 * math.pi * (xs / (0.09 * self.w) + ph * 2)) * self.highlight
        return map_x + dx.astype(np.float32), map_y + dy.astype(np.float32)

    def glow(self, frame, ph):
        g = 1.0 + 0.10 * self.amp * self.highlight * math.sin(2 * math.pi * ph)
        return np.clip(frame.astype(np.float32) * g[..., None], 0, 255).astype(np.uint8)

    # --- 粒子
    def particles(self, frame, ph):
        if self.pcolor is None or len(self.px) == 0:
            return frame
        h2, w2 = self.h // 2, self.w // 2
        layer = np.zeros((h2, w2, 3), np.float32)
        col = np.array(self.pcolor, np.float32) / 255.0
        y = (self.py - ph * self.pk * self.h) % self.h
        x = self.px + self.pwig * np.sin(2 * math.pi * (ph * self.pwm + self.pph))
        tw = 0.35 + 0.65 * (0.5 + 0.5 * np.sin(2 * math.pi * (ph * self.pn + self.pph)))
        scale = 0.6 + 0.8 * self.pdepth  # 近的大一点亮一点
        for i in range(len(x)):
            r = max(1, int(self.pr[i] * scale[i]))
            c = (col * 0.85 * tw[i] * (0.5 + 0.5 * scale[i])).tolist()
            cv2.circle(layer, (int(x[i] / 2), int(y[i] / 2)), r, c, -1, lineType=cv2.LINE_AA)
        layer = cv2.GaussianBlur(layer, (0, 0), 1.2)
        glow = cv2.GaussianBlur(layer, (0, 0), 6) * 0.6
        layer = cv2.resize(layer + glow, (self.w, self.h), interpolation=cv2.INTER_LINEAR)
        out = frame.astype(np.float32) / 255.0
        out = 1 - (1 - out) * (1 - np.clip(layer, 0, 1))  # screen 混合
        return (np.clip(out, 0, 1) * 255).astype(np.uint8)

    # --- 两层 3D
    def layers(self):
        if self._layers is not None:
            return self._layers
        d8 = (self.depth * 255).astype(np.uint8)
        thr, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        near = (d8 > thr).astype(np.uint8) * 255
        near = cv2.morphologyEx(near, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
        hole = cv2.dilate(near, np.ones((15, 15), np.uint8))
        small = cv2.resize(self.img, (self.w // 3, self.h // 3), interpolation=cv2.INTER_AREA)
        hole_s = cv2.resize(hole, (self.w // 3, self.h // 3), interpolation=cv2.INTER_NEAREST)
        bg = cv2.inpaint(small, hole_s, 9, cv2.INPAINT_TELEA)
        bg = cv2.resize(bg, (self.w, self.h), interpolation=cv2.INTER_CUBIC)
        bg = np.where(hole[..., None] > 0, cv2.GaussianBlur(bg, (0, 0), 4), self.img)
        alpha = cv2.GaussianBlur(near.astype(np.float32) / 255.0, (0, 0), 2.5)
        self._layers = (alpha, bg)
        return self._layers

    def export_layers(self, out_dir, name):
        alpha, bg = self.layers()
        fg = np.dstack([self.img, (alpha * 255).astype(np.uint8)])
        cv2.imwrite(os.path.join(out_dir, f"{name}-fg.png"), fg)
        cv2.imwrite(os.path.join(out_dir, f"{name}-bg.png"), bg)

    def layers_frame(self, ph):
        alpha, bg = self.layers()
        ox, oy = path_offset(ph, self.ax, self.ay)
        m = self.margin
        bigbg = cv2.resize(bg, (self.w + 2 * m, self.h + 2 * m), interpolation=cv2.INTER_CUBIC)
        bg_f = cv2.remap(bigbg, self.base_x - 0.45 * ox, self.base_y - 0.45 * oy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        M = np.float32([[1, 0, 0.75 * ox], [0, 1, 0.75 * oy]])
        fg_f = cv2.warpAffine(self.img, M, (self.w, self.h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        a_f = cv2.warpAffine(alpha, M, (self.w, self.h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)[..., None]
        return (fg_f * a_f + bg_f * (1 - a_f)).astype(np.uint8)

    # --- Ken Burns
    def kenburns_frame(self, ph):
        z = 1.0 + 0.06 * self.amp * (0.5 - 0.5 * math.cos(2 * math.pi * ph))
        px = 0.015 * self.w * self.amp * math.sin(2 * math.pi * ph)
        cx, cy = self.w / 2 + px, self.h / 2
        M = np.float32([[z, 0, self.w / 2 - z * cx], [0, z, self.h / 2 - z * cy]])
        return cv2.warpAffine(self.img, M, (self.w, self.h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)

    # --- 一帧
    def frame(self, mode, ph):
        if mode == "kenburns":
            return self.kenburns_frame(ph)
        if mode == "layers":
            return self.layers_frame(ph)
        if mode == "particles":
            return self.particles(self.img, ph)
        if mode == "shimmer":
            mx, my = self.shimmer_maps(ph, self.base_x, self.base_y)
            return self.glow(self.warp(mx, my), ph)
        if mode == "parallax":
            mx, my = self.parallax_maps(ph)
            return self.warp(mx, my)
        if mode == "combo":
            mx, my = self.parallax_maps(ph)
            mx, my = self.shimmer_maps(ph, mx, my)
            return self.particles(self.glow(self.warp(mx, my), ph), ph)
        sys.exit(f"未知模式 {mode}")


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--depth")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name")
    ap.add_argument("--modes", default="combo")
    ap.add_argument("--seconds", type=float, default=6)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size", help="WxH，默认原图尺寸")
    ap.add_argument("--amp", type=float, default=1.0)
    ap.add_argument("--focus", type=float, default=0.45, help="视差不动的深度（0 远 1 近）")
    ap.add_argument("--particles", default="gold", choices=list(PARTICLE_COLORS) + ["none"])
    ap.add_argument("--n-particles", type=int, default=110)
    ap.add_argument("--highlight", default="lum", choices=["lum", "sat"], help="流光/辉光蒙版：lum=按亮度（深色画）；sat=亮且有颜色（白纸底的画）")
    ap.add_argument("--gif", action="store_true")
    ap.add_argument("--export-layers", action="store_true")
    a = ap.parse_args()

    size = tuple(int(v) for v in a.size.lower().split("x")) if a.size else None
    img = load_image(a.image, size)
    modes = [m.strip() for m in a.modes.split(",") if m.strip()]
    need_depth = any(m in ("parallax", "layers", "combo") for m in modes)
    depth = load_depth(a.depth, img.shape) if (a.depth and os.path.exists(a.depth)) else None
    if need_depth and depth is None:
        sys.exit("parallax / layers / combo 需要 --depth（先跑 depth_midas.py）")
    name = a.name or os.path.splitext(os.path.basename(a.image))[0]
    os.makedirs(a.out, exist_ok=True)
    scene = Scene(img, depth, amp=a.amp, focus=a.focus, particles=a.particles, n_particles=a.n_particles, highlight=a.highlight)
    n = int(round(a.seconds * a.fps))
    h, w = img.shape[:2]
    for mode in modes:
        path = os.path.join(a.out, f"{name}-{mode}.mp4")
        wr = Writer(path, w, h, a.fps)
        for i in range(n):
            wr.write(scene.frame(mode, i / n))
        wr.close()
        print(f"[live] {path}  {w}x{h} {a.seconds}s@{a.fps}fps  {os.path.getsize(path)//1024} KB")
        if a.gif:
            to_gif(path, path[:-4] + ".gif")
            print("[gif ]", path[:-4] + ".gif")
    if a.export_layers or "layers" in modes:
        scene.export_layers(a.out, name)
        print("[layers]", os.path.join(a.out, f"{name}-fg.png"), os.path.join(a.out, f"{name}-bg.png"))


if __name__ == "__main__":
    main()
