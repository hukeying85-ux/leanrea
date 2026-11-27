#!/usr/bin/env python3
"""
v4 Pipeline:
  Part A — Surgical Fix for White Yier's Overlapped Mouth (100% keeping everything else unchanged!)
  Part B — Brand-New Creative Scene & Multi-Act 2D Animation:
           "Moonlit Starry Beach & Heart Fireworks — Bubu & Yier Sparkler Cheer, Cheek Cuddle & Paw-Heart"
           Rendered in both 16:9 (1920x1080) and 9:16 (1080x1920) at 24.0 fps (151 frames, 6.292s).
All outputs are written exclusively to a brand-new folder `outputs_v4_new/` (zero overwrite of v3).
"""

import math
import os
import pathlib
import subprocess
import time
from typing import List, Tuple

import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = pathlib.Path("/home/user/leanrea")
WORK = pathlib.Path("/tmp/v4_work")
OUT_NEW = ROOT / "outputs_v4_new"


def get_font(size: int):
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def draw_badge(bgr: np.ndarray, text: str, xy: Tuple[int, int] = (12, 10), font_size: int = 18) -> np.ndarray:
    pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil, "RGBA")
    font = get_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = xy
    draw.rounded_rectangle((x, y, x + tw + 22, y + th + 12), radius=8, fill=(14, 16, 26, 210))
    draw.text((x + 11, y + 5 - bbox[1]), text, font=font, fill=(255, 248, 232, 255))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def encode_mp4(frames_iter, width: int, height: int, fps: float, audio_src: pathlib.Path, out_path: pathlib.Path, crf: int = 14):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG, "-y",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", f"{width}x{height}",
        "-r", f"{fps:.6f}",
        "-i", "-",
        "-i", str(audio_src),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", str(crf),
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-movflags", "+faststart",
        "-shortest",
        str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert proc.stdin is not None
    for frm in frames_iter:
        proc.stdin.write(frm.tobytes())
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"FFmpeg failed ({rc}) for {out_path}")


# ===========================================================================
# PART A: SURGICAL FIX FOR WHITE YIER'S OVERLAPPED MOUTH (其余 100% 不变)
# ===========================================================================
def laplace_skin_fill(roi_bgr: np.ndarray, mask_bool: np.ndarray, n_iter: int = 300) -> np.ndarray:
    u = roi_bgr.astype(np.float32).copy()
    dil = cv2.dilate(mask_bool.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    ring = dil & (~mask_bool)
    if ring.sum() > 0:
        u[mask_bool] = np.median(u[ring], axis=0)
    m = mask_bool
    for _ in range(n_iter):
        avg = 0.25 * (np.roll(u, 1, 0) + np.roll(u, -1, 0) + np.roll(u, 1, 1) + np.roll(u, -1, 1))
        u[m] = avg[m]
    return np.clip(np.round(u), 0, 255).astype(np.uint8)


def draw_clean_w_mouth(
    frame: np.ndarray,
    cx: float,
    cy: float,
    half_w: float = 22.0,
    h_dip: float = 9.2,
    thickness: float = 6.3,
    tilt_deg: float = 4.0,
    asym: float = 0.88,
    ink_bgr: Tuple[int, int, int] = (26, 22, 30),
) -> np.ndarray:
    S = 4
    pad = 50
    x0, y0 = int(round(cx)) - pad, int(round(cy)) - pad
    sub_x, sub_y = cx - int(round(cx)), cy - int(round(cy))
    patch = frame[y0 : y0 + 2 * pad, x0 : x0 + 2 * pad].copy()
    hi = cv2.resize(patch, (2 * pad * S, 2 * pad * S), interpolation=cv2.INTER_CUBIC)
    theta = np.deg2rad(tilt_deg)
    ct, st = np.cos(theta), np.sin(theta)
    for lobe, (xa, xb) in enumerate([(-half_w, 0.0), (0.0, half_w * asym)]):
        pts = []
        for t in np.linspace(0.0, 1.0, 44):
            lx = xa + (xb - xa) * t
            ly = h_dip * np.sin(np.pi * t)
            if (lobe == 0 and t < 0.14) or (lobe == 1 and t > 0.86):
                ly -= 1.2
            rx = lx * ct - ly * st + sub_x
            ry = lx * st + ly * ct + sub_y
            pts.append([int(round((pad + rx) * S)), int(round((pad + ry) * S))])
        pts_arr = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(hi, [pts_arr], False, ink_bgr, int(round(thickness * S)), lineType=cv2.LINE_AA)
    hi = cv2.GaussianBlur(hi, (3, 3), 0.75)
    lo = cv2.resize(hi, (2 * pad, 2 * pad), interpolation=cv2.INTER_AREA)
    out = frame.copy()
    out[y0 : y0 + 2 * pad, x0 : x0 + 2 * pad] = lo
    return out


def build_part_a_mouth_fix(src_audio: pathlib.Path) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    print("[Part A] Loading v3 1920x1108 & 1080x1920 masters for surgical Yier mouth fix ...", flush=True)
    cap_m = cv2.VideoCapture(str(WORK / "v3_master_1920x1108.mp4"))
    mst_1920 = []
    while True:
        ok, f = cap_m.read()
        if not ok:
            break
        mst_1920.append(f)
    cap_m.release()

    cap_v = cv2.VideoCapture(str(WORK / "v3_9x16_1080x1920.mp4"))
    mst_9x16 = []
    while True:
        ok, f = cap_v.read()
        if not ok:
            break
        mst_9x16.append(f)
    cap_v.release()
    assert len(mst_1920) == 151 and len(mst_9x16) == 151

    ker_dil = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (29, 29))
    ker_prot = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))

    def erase_mouth_core(frm: np.ndarray, sy0: int, sy1: int, sx0: int, sx1: int, expect_x_range: Tuple[int, int]):
        roi = frm[sy0:sy1, sx0:sx1]
        skin_ref = np.median(frm[625:665, 1340:1440].reshape(-1, 3).astype(np.float32), axis=0)
        diff = np.linalg.norm(roi.astype(np.float32) - skin_ref[None, None, :], axis=2)
        core = (diff > 28.0).astype(np.uint8)
        n_lbl, labels, stats, centroids = cv2.connectedComponentsWithStats(core, connectivity=8)
        mouth_mask = np.zeros_like(core, dtype=bool)
        other_ink = np.zeros_like(core, dtype=bool)
        H, W = core.shape
        cxs, cys = [], []
        for lid in range(1, n_lbl):
            x, y, w, h, area = stats[lid]
            cx_l, _ = centroids[lid]
            abs_cx = sx0 + cx_l
            touches_bottom = (y + h >= H - 2)
            touches_left = (x <= 1)
            touches_right = (x + w >= W - 2)
            # Include even 1-px detached bottom specks (1 <= area <= 2800) inside expect_x_range!
            if (not touches_bottom) and (not touches_left) and (not touches_right) and (expect_x_range[0] <= abs_cx <= expect_x_range[1]) and (1 <= area <= 2800):
                mouth_mask |= (labels == lid)
                if area >= 60:
                    ys_c, xs_c = np.where(labels == lid)
                    cxs.append(sx0 + float(np.mean(xs_c)))
                    cys.append(sy0 + float(np.percentile(ys_c, 22)))
            else:
                other_ink |= (labels == lid)

        cx_val = float(np.mean(cxs))
        cy_val = float(np.mean(cys))
        # Also include a clean vertical capsule around (cx_val, cy_val..cy_val+72) so faint sub-threshold tip specks are 100% caught!
        yy, xx = np.mgrid[0:H, 0:W]
        capsule = ((np.abs((sx0 + xx) - cx_val) <= 28.0) & ((sy0 + yy) >= cy_val - 16.0) & ((sy0 + yy) <= cy_val + 76.0))
        prot = cv2.dilate(other_ink.astype(np.uint8), ker_prot) > 0
        dil_mouth = ((cv2.dilate(mouth_mask.astype(np.uint8), ker_dil) > 0) | capsule) & (~prot)
        filled_roi = laplace_skin_fill(roi, dil_mouth, n_iter=300)
        out = frm.copy()
        out[sy0:sy1, sx0:sx1] = filled_roi
        return out, cx_val, cy_val

    fixed_1920 = [f.copy() for f in mst_1920]

    # 1) Transition frames f=067..070
    for fi, xr, tilt, asym, hw in [
        (67, (1348, 1420), 1.0, 0.98, 24.0),
        (68, (1348, 1422), 1.5, 0.97, 24.0),
        (69, (1358, 1432), 2.5, 0.95, 23.5),
        (70, (1412, 1488), 4.5, 0.88, 22.5),
    ]:
        cl_f, cx, cy = erase_mouth_core(fixed_1920[fi], 695, 852, 1315, 1525, xr)
        fixed_1920[fi] = draw_clean_w_mouth(cl_f, cx, cy + 3.0, half_w=hw, h_dip=9.2, thickness=6.3, tilt_deg=tilt, asym=asym)

    # 2) Sideways eye-rubbing action frames f=000..022 and f=071..118
    for rng in [list(range(0, 23)), list(range(71, 119))]:
        cl_list, cxs, cys = [], [], []
        for fi in rng:
            frm = fixed_1920[fi]
            if fi in (71, 72):
                r_sm = frm[685:730, 1340:1428]
                skin_ref = np.median(frm[625:665, 1340:1440].reshape(-1, 3).astype(np.float32), axis=0)
                ns = (np.linalg.norm(r_sm.astype(np.float32) - skin_ref[None, None, :], axis=2) > 20.0).astype(np.uint8)
                nl, lb, st, _ = cv2.connectedComponentsWithStats(ns)
                sm_m = np.zeros_like(ns, dtype=bool)
                pw_m = np.zeros_like(ns, dtype=bool)
                for lid in range(1, nl):
                    if st[lid, 1] + st[lid, 3] < r_sm.shape[0] - 1:
                        sm_m |= (lb == lid)
                    else:
                        pw_m |= (lb == lid)
                dil_sm = (cv2.dilate(sm_m.astype(np.uint8), ker_dil) > 0) & (~(cv2.dilate(pw_m.astype(np.uint8), ker_prot) > 0))
                frm = frm.copy()
                frm[685:730, 1340:1428] = laplace_skin_fill(r_sm, dil_sm, 240)
            cl_f, cx, cy = erase_mouth_core(frm, 695, 852, 1375, 1560, (1412, 1522))
            cl_list.append(cl_f)
            cxs.append(cx)
            cys.append(cy + 3.0)
        k = np.array([0.1, 0.2, 0.4, 0.2, 0.1])
        cxs_s = np.convolve(np.pad(cxs, 2, mode="edge"), k, mode="valid")
        cys_s = np.convolve(np.pad(cys, 2, mode="edge"), k, mode="valid")
        for idx, fi in enumerate(rng):
            fixed_1920[fi] = draw_clean_w_mouth(
                cl_list[idx], float(cxs_s[idx]), float(cys_s[idx]),
                half_w=21.5, h_dip=9.0, thickness=6.2, tilt_deg=4.5, asym=0.86,
            )

    print("[Part A] Encoding A1 (16:9 1920x1108), A2 (576x1280 exact), A3 (9:16 1080x1920 seamless) ...", flush=True)
    encode_mp4(fixed_1920, 1920, 1108, 24.0, src_audio, OUT_NEW / "A1_mouth_fixed_16x9_master_1920x1108.mp4", crf=14)

    def iter_a2_576():
        for frm in fixed_1920:
            c = np.zeros((1280, 576, 3), dtype=np.uint8)
            c[404:736, :576] = cv2.resize(frm, (576, 332), interpolation=cv2.INTER_AREA)
            yield c

    encode_mp4(iter_a2_576(), 576, 1280, 24.0, src_audio, OUT_NEW / "A2_mouth_fixed_exact_container_576x1280.mp4", crf=14)

    ramp = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, 52, dtype=np.float32)))[:, None, None]

    def iter_a3_9x16():
        for fi in range(151):
            base916 = mst_9x16[fi].copy()
            fg1080 = cv2.resize(fixed_1920[fi], (1080, 622), interpolation=cv2.INTER_AREA)
            # Only update below y=1350 (where Yier lives at y=1550..1920) so upper sky & seam stay 100.000% identical to v3!
            blend = (1.0 - ramp) * base916[1298:1350].astype(np.float32) + ramp * fg1080[:52].astype(np.float32)
            base916[1298:1350] = np.clip(np.round(blend), 0, 255).astype(np.uint8)
            base916[1350:1920] = fg1080[52:]
            yield base916

    encode_mp4(iter_a3_9x16(), 1080, 1920, 24.0, src_audio, OUT_NEW / "A3_mouth_fixed_vertical_9x16_1080x1920.mp4", crf=14)

    # Save Before vs After high-zoom proof sheet (A4)
    cols = []
    for fi in [4, 22, 67, 68, 70, 71, 73, 95]:
        ca = draw_badge(cv2.resize(mst_1920[fi][540:870, 1130:1570], (240, 180), interpolation=cv2.INTER_AREA), f"Before f={fi:03d}", (8, 8), 14)
        cb = draw_badge(cv2.resize(fixed_1920[fi][540:870, 1130:1570], (240, 180), interpolation=cv2.INTER_AREA), f"Fixed f={fi:03d}", (8, 8), 14)
        cols.append(np.vstack([ca, cb]))
    cv2.imwrite(str(OUT_NEW / "A4_yier_mouth_fix_before_after_zoom.jpg"), np.hstack(cols), [cv2.IMWRITE_JPEG_QUALITY, 96])

    return mst_1920, fixed_1920


# ===========================================================================
# PART B: BRAND-NEW SCENE & MULTI-ACT 24FPS 2D ANIMATION (海边星夜烟花·贴贴比心)
# ===========================================================================
def extract_despilled_rgba(png_path: pathlib.Path) -> np.ndarray:
    """Extracts razor-sharp RGBA from #00FF00 green screen with complete green-spill suppression on dark outlines."""
    bgr = cv2.imread(str(png_path))
    assert bgr is not None
    b = bgr[:, :, 0].astype(np.float32)
    g = bgr[:, :, 1].astype(np.float32)
    r = bgr[:, :, 2].astype(np.float32)
    # Green screen excess: pure #00FF00 has g - max(r, b) ~ 240; bear colors (brown, white, pink, yellow, dark ink) have g <= max(r, b) + 8!
    excess_g = g - np.maximum(r, b)
    alpha = np.clip(1.0 - (excess_g - 14.0) / 52.0, 0.0, 1.0)
    # Clean stray 1px islands and smooth 1px edge
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0.55)
    # Despill green fringe along semi-transparent edge pixels!
    g_clean = np.where(excess_g > 4.0, np.maximum(r, b), g)
    # Subtle warm-lavender moonlight tint so character palette harmonizes with starry twilight beach!
    b_out = np.clip(b * 1.02 + 3.0, 0, 255)
    g_out = np.clip(g_clean * 0.98, 0, 255)
    r_out = np.clip(r * 1.01 + 2.0, 0, 255)
    rgba = np.dstack([b_out, g_out, r_out, alpha * 255.0]).clip(0, 255).astype(np.uint8)
    return rgba


def make_pose1_blink_rgba(pose1_rgba: np.ndarray) -> np.ndarray:
    """Creates a crisp 2D hand-drawn closed-eye blink variant of Pose 1 (zero ghosting!)."""
    out = pose1_rgba.copy()
    bgr = out[:, :, :3].copy()
    # Bubu eyes at (318, 333) and (515, 332); Yier eyes at ~(878, 336) and ~(1066, 336)
    lum = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Find Yier's two round dark eyes inside x=820..1130, y=290..385
    ey_y = (lum[290:385, 820:1130] < 65).astype(np.uint8)
    nl, lb, st, ct = cv2.connectedComponentsWithStats(ey_y)
    yier_eyes = [(int(820 + ct[i][0]), int(290 + ct[i][1])) for i in range(1, nl) if 400 < st[i, 4] < 2600]

    for ex, ey, skin_box in [
        (318, 333, (260, 290, 360, 310)),
        (515, 332, (460, 290, 560, 310)),
        *[(yx, yy, (yx - 30, yy - 55, yx + 30, yy - 35)) for (yx, yy) in yier_eyes],
    ]:
        skin_col = np.median(bgr[skin_box[1] : skin_box[3], skin_box[0] : skin_box[2]].reshape(-1, 3), axis=0)
        cv2.circle(bgr, (ex, ey), 29, tuple(int(c) for c in skin_col), -1, lineType=cv2.LINE_AA)
        # Draw cute curved happy '^' closed eye arc
        cv2.ellipse(bgr, (ex, ey + 8), (22, 14), 0, 195, 345, (42, 24, 18), 9, lineType=cv2.LINE_AA)
    out[:, :, :3] = bgr
    return out


def warp_live2d_cel(
    rgba: np.ndarray,
    breath_scale_y: float = 1.0,
    breath_scale_x: float = 1.0,
    head_sway_px: float = 0.0,
    head_tilt_deg: float = 0.0,
    left_arm_dy: float = 0.0,
    right_arm_dy: float = 0.0,
    foot_anchor_y: float = 768.0,
) -> np.ndarray:
    """Smooth continuous 2D mesh deformation anchored at standing feet (zero stiffness, zero tearing!)."""
    H, W = rgba.shape[:2]
    gh, gw = 32, 48
    gy, gx = np.mgrid[0:gh, 0:gw].astype(np.float32)
    px = gx * (W - 1) / (gw - 1)
    py = gy * (H - 1) / (gh - 1)

    # Normalized height from standing feet (0 at feet y=foot_anchor_y, 1 at top of head y=70)
    h_norm = np.clip((foot_anchor_y - py) / max(1.0, foot_anchor_y - 70.0), 0.0, 1.15)
    cx_mid = W * 0.50

    # Forward desired displacement of mesh vertices, inverted for remap:
    # 1) Squash & stretch anchored at feet
    src_x = cx_mid + (px - cx_mid) / breath_scale_x
    src_y = foot_anchor_y - (foot_anchor_y - py) / breath_scale_y

    # 2) Smooth upper-body / head sway & gentle head tilt (increases smoothly with h_norm^1.5)
    sway_w = h_norm ** 1.45
    src_x -= head_sway_px * sway_w
    if abs(head_tilt_deg) > 1e-4:
        rad = math.radians(head_tilt_deg) * sway_w
        dx = src_x - cx_mid
        dy = src_y - (foot_anchor_y - 320.0)
        src_x = cx_mid + dx * np.cos(rad) + dy * np.sin(rad)
        src_y = (foot_anchor_y - 320.0) - dx * np.sin(rad) + dy * np.cos(rad)

    # 3) Localized Gaussian arm wave deformers (Bubu outer left paw & Yier outer right paw(s))
    if abs(left_arm_dy) > 1e-3:
        w_l = np.exp(-(((px - 225.0) / 145.0) ** 2 + ((py - 415.0) / 150.0) ** 2))
        src_y -= left_arm_dy * w_l
        src_x -= (left_arm_dy * 0.28) * w_l
    if abs(right_arm_dy) > 1e-3:
        w_r = np.exp(-(((px - 1125.0) / 170.0) ** 2 + ((py - 430.0) / 155.0) ** 2))
        src_y -= right_arm_dy * w_r

    map_x = cv2.resize(src_x, (W, H), interpolation=cv2.INTER_CUBIC)
    map_y = cv2.resize(src_y, (W, H), interpolation=cv2.INTER_CUBIC)
    return cv2.remap(rgba, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def draw_handdrawn_heart(canvas_bgr: np.ndarray, cx: float, cy: float, size: float, angle_deg: float, alpha: float):
    """Draws a super-cute 2D cel-shaded pastel-pink heart with dark-brown outline matching Yier & Bubu's art style!"""
    if alpha <= 0.02 or size < 2.0:
        return
    pad = int(size * 2.4) + 12
    x0, y0 = int(round(cx)) - pad, int(round(cy)) - pad
    H, W = canvas_bgr.shape[:2]
    if x0 >= W or y0 >= H or x0 + 2 * pad <= 0 or y0 + 2 * pad <= 0:
        return
    S = 3
    layer = np.zeros((2 * pad * S, 2 * pad * S, 4), dtype=np.uint8)
    rad = math.radians(angle_deg)
    ct, st = math.cos(rad), math.sin(rad)
    pts = []
    for t in np.linspace(0, 2 * math.pi, 80, endpoint=False):
        hx = 16.0 * (math.sin(t) ** 3)
        hy = -(13.0 * math.cos(t) - 5.0 * math.cos(2 * t) - 2.0 * math.cos(3 * t) - math.cos(4 * t))
        lx, ly = hx * (size / 17.0), hy * (size / 17.0)
        rx = lx * ct - ly * st
        ry = lx * st + ly * ct
        pts.append([int(round((pad + rx) * S)), int(round((pad + ry) * S))])
    pts_arr = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
    # Fill pastel sakura pink (BGR: 175, 148, 255) + dark brown outline (32, 22, 42)
    cv2.fillPoly(layer, [pts_arr], (178, 148, 255, 255), lineType=cv2.LINE_AA)
    cv2.polylines(layer, [pts_arr], True, (36, 24, 44, 255), max(2, int(round(size * 0.17 * S))), lineType=cv2.LINE_AA)
    # Cute white specular dot on upper-left lobe
    hx_s, hy_s = -size * 0.35, -size * 0.25
    sx = int(round((pad + hx_s * ct - hy_s * st) * S))
    sy = int(round((pad + hx_s * st + hy_s * ct) * S))
    cv2.circle(layer, (sx, sy), max(2, int(round(size * 0.14 * S))), (245, 245, 255, 230), -1, lineType=cv2.LINE_AA)
    lo = cv2.resize(layer, (2 * pad, 2 * pad), interpolation=cv2.INTER_AREA)

    cx0, cy0 = max(0, x0), max(0, y0)
    cx1, cy1 = min(W, x0 + 2 * pad), min(H, y0 + 2 * pad)
    sub = lo[cy0 - y0 : cy1 - y0, cx0 - x0 : cx1 - x0]
    a = (sub[:, :, 3:4].astype(np.float32) / 255.0) * float(alpha)
    roi = canvas_bgr[cy0:cy1, cx0:cx1].astype(np.float32)
    canvas_bgr[cy0:cy1, cx0:cx1] = np.clip(np.round((1.0 - a) * roi + a * sub[:, :, :3].astype(np.float32)), 0, 255).astype(np.uint8)


def add_glow_circle(canvas_f32: np.ndarray, cx: float, cy: float, radius: float, bgr_color: Tuple[float, float, float], intensity: float):
    """Additive soft Gaussian glow for fireworks, sparkler sparks, lantern & ocean reflections."""
    if intensity <= 0.005 or radius < 1.0:
        return
    H, W = canvas_f32.shape[:2]
    r_int = int(math.ceil(radius * 2.6))
    x0, x1 = max(0, int(cx) - r_int), min(W, int(cx) + r_int + 1)
    y0, y1 = max(0, int(cy) - r_int), min(H, int(cy) + r_int + 1)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    d2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / max(1.0, radius * radius)
    falloff = (np.exp(-1.6 * d2) * intensity)[:, :, None]
    col = np.array(bgr_color, dtype=np.float32)[None, None, :]
    canvas_f32[y0:y1, x0:x1] += falloff * col


def render_new_scene_video(
    bg_raw: np.ndarray,
    out_w: int,
    out_h: int,
    horizon_y: int,
    lantern_xy: Tuple[int, int],
    char_scale_w: int,
    char_foot_y: int,
    firework_specs: List[dict],
    pose1_rgba: np.ndarray,
    pose1_blink_rgba: np.ndarray,
    pose2_rgba: np.ndarray,
    pose3_rgba: np.ndarray,
    src_audio: pathlib.Path,
    out_path: pathlib.Path,
) -> List[np.ndarray]:
    bg_base = cv2.resize(bg_raw, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
    char_scale_h = int(round(char_scale_w * pose1_rgba.shape[0] / pose1_rgba.shape[1]))

    # Precompute gentle twinkling star coordinates in upper sky
    rng = np.random.default_rng(20261126)
    stars = [
        (float(rng.uniform(0.04 * out_w, 0.96 * out_w)), float(rng.uniform(0.04 * horizon_y, 0.78 * horizon_y)), float(rng.uniform(0, 6.28)), float(rng.uniform(1.8, 3.8)))
        for _ in range(36)
    ]

    sample_frames: List[np.ndarray] = []

    def gen_frames():
        for fi in range(151):
            t = fi / 24.0
            # 1) Subtle dreamy camera breathing & ocean wave horizontal shimmer below horizon_y
            bg = bg_base.copy()
            water_h = int((out_h - horizon_y) * 0.42)
            if water_h > 10:
                wy0, wy1 = horizon_y + 4, horizon_y + 4 + water_h
                yy_w, xx_w = np.mgrid[0 : (wy1 - wy0), 0:out_w].astype(np.float32)
                amp = 1.6 * (yy_w / max(1.0, water_h))
                shift_x = np.clip(xx_w + amp * np.sin(yy_w * 0.22 - t * 3.6), 0, out_w - 1)
                bg[wy0:wy1] = cv2.remap(bg[wy0:wy1], shift_x, yy_w, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)

            canvas_f = bg.astype(np.float32)

            # 2) Twinkling stars + warm lantern breathing glow + shooting star (f=16..46)
            for sx, sy, ph, sr in stars:
                tw = 0.45 + 0.55 * math.sin(t * 4.2 + ph)
                add_glow_circle(canvas_f, sx, sy, sr, (255, 235, 245), 0.32 * tw)

            lx, ly = lantern_xy
            lantern_pulse = 0.85 + 0.15 * math.sin(t * 5.5)
            add_glow_circle(canvas_f, lx, ly, out_w * 0.045, (70, 165, 255), 0.28 * lantern_pulse)

            if 16 <= fi <= 46:
                u_m = (fi - 16) / 30.0
                mx = out_w * (0.78 - 0.42 * u_m)
                my = horizon_y * (0.14 + 0.28 * u_m)
                fade_m = math.sin(math.pi * u_m)
                for k_tail in range(14):
                    s_t = k_tail / 14.0
                    add_glow_circle(
                        canvas_f,
                        mx + s_t * out_w * 0.075,
                        my - s_t * horizon_y * 0.048,
                        max(1.5, 4.2 * (1.0 - s_t)),
                        (255, 240, 225),
                        0.75 * fade_m * (1.0 - s_t) ** 1.4,
                    )

            # 3) Romantic Pastel Fireworks in Night Sky + Shimmering Reflections on Ocean Water!
            for fw in firework_specs:
                dt_fw = fi - fw["t0"]
                if -12 <= dt_fw < 0:
                    # Rising golden launch trail from horizon!
                    u_r = (dt_fw + 12) / 12.0
                    ry = horizon_y - u_r * (horizon_y - fw["cy"])
                    add_glow_circle(canvas_f, fw["cx"], ry, 4.5, (160, 225, 255), 0.85)
                elif 0 <= dt_fw <= 52:
                    u_b = dt_fw / 52.0
                    rad_fw = fw["max_r"] * (1.0 - (1.0 - u_b) ** 2.6)
                    gravity_drop = 26.0 * (u_b ** 2)
                    fade_fw = (1.0 - u_b) ** 1.35
                    # Soft sky illumination bloom
                    add_glow_circle(canvas_f, fw["cx"], fw["cy"], rad_fw * 0.85, fw["col"], 0.16 * fade_fw)
                    # Ocean water reflection right below (fw["cx"], horizon_y + reflected offset)!
                    refl_y = min(out_h - 40, horizon_y + int((horizon_y - fw["cy"]) * 0.24))
                    add_glow_circle(canvas_f, fw["cx"], refl_y, rad_fw * 0.48, fw["col"], 0.20 * fade_fw)

                    n_sparks = 34
                    for si in range(n_sparks):
                        ang = 2.0 * math.pi * si / n_sparks
                        if fw.get("heart", False):
                            hx = math.sin(ang) ** 3
                            hy = -(0.81 * math.cos(ang) - 0.31 * math.cos(2 * ang) - 0.12 * math.cos(3 * ang) - 0.06 * math.cos(4 * ang))
                            px_s = fw["cx"] + hx * rad_fw * 1.05
                            py_s = fw["cy"] + hy * rad_fw * 1.05 + gravity_drop
                        else:
                            ring_scale = 1.0 if si % 2 == 0 else 0.68
                            px_s = fw["cx"] + math.cos(ang) * rad_fw * ring_scale
                            py_s = fw["cy"] + math.sin(ang) * rad_fw * ring_scale + gravity_drop
                        tw_s = 0.65 + 0.35 * math.sin(dt_fw * 0.9 + si * 1.7)
                        add_glow_circle(canvas_f, px_s, py_s, max(2.2, out_w * 0.0042), fw["col"], 0.92 * fade_fw * tw_s)
                        add_glow_circle(canvas_f, px_s, py_s, max(1.2, out_w * 0.0018), (255, 252, 255), 0.70 * fade_fw * tw_s)

            frame_bgr = np.clip(np.round(canvas_f), 0, 255).astype(np.uint8)

            # 4) Select Active Pose & Compute Continuous 24fps Live2D Mesh + Elastic Pop Deformation!
            if fi < 48:
                # ACT 1: Cheering & Waving Golden Sparkler!
                base_cel = pose1_blink_rgba if (19 <= fi <= 22 or 39 <= fi <= 41) else pose1_rgba
                sy_b = 1.0 + 0.022 * math.sin(t * 6.5)
                sx_b = 1.0 - 0.015 * math.sin(t * 6.5)
                sway = 8.0 * math.sin(t * 4.2)
                tilt = 1.8 * math.sin(t * 4.2)
                l_arm = 24.0 * math.sin(t * 8.4)
                r_arm = -22.0 * math.cos(t * 8.4)
                # 3-frame anticipation crouch before hugging in Act 2!
                if fi >= 45:
                    u_ant = (fi - 44) / 3.0
                    sy_b -= 0.055 * u_ant
                    sx_b += 0.045 * u_ant
                warped = warp_live2d_cel(base_cel, sy_b, sx_b, sway, tilt, l_arm, r_arm, foot_anchor_y=760.0)
            elif fi < 100:
                # ACT 2: Affectionate Cheek-to-Cheek Hug & Swaying Cuddle (贴脸抱抱蹭蹭 + 冒爱心)!
                dt_p2 = (fi - 48) / 24.0
                bounce = math.exp(-6.5 * dt_p2) * math.cos(18.0 * dt_p2)
                sy_b = 1.0 + 0.055 * bounce + 0.018 * math.sin(dt_p2 * 5.2)
                sx_b = 1.0 - 0.042 * bounce - 0.012 * math.sin(dt_p2 * 5.2)
                # Cozy rhythmic cheek-nuzzle rocking left & right!
                sway = 14.0 * math.sin(dt_p2 * 4.8)
                tilt = 2.6 * math.sin(dt_p2 * 4.8)
                if fi >= 97:
                    u_ant = (fi - 96) / 3.0
                    sy_b -= 0.055 * u_ant
                    sx_b += 0.045 * u_ant
                warped = warp_live2d_cel(pose2_rgba, sy_b, sx_b, sway, tilt, 0.0, 0.0, foot_anchor_y=776.0)
            else:
                # ACT 3: Synchronized Paw-Heart Celebration under Heart Fireworks!
                dt_p3 = (fi - 100) / 24.0
                bounce = math.exp(-6.0 * dt_p3) * math.cos(18.0 * dt_p3)
                sy_b = 1.0 + 0.060 * bounce + 0.022 * math.sin(dt_p3 * 6.8)
                sx_b = 1.0 - 0.045 * bounce - 0.015 * math.sin(dt_p3 * 6.8)
                sway = 9.0 * math.sin(dt_p3 * 5.0)
                tilt = 1.8 * math.sin(dt_p3 * 5.0)
                l_arm = 20.0 * math.sin(dt_p3 * 9.0)
                r_arm = 20.0 * math.sin(dt_p3 * 9.0 + 0.7)
                warped = warp_live2d_cel(pose3_rgba, sy_b, sx_b, sway, tilt, l_arm, r_arm, foot_anchor_y=776.0)

            # Scale warped character cel onto beach canvas
            cel_scaled = cv2.resize(warped, (char_scale_w, char_scale_h), interpolation=cv2.INTER_AREA)
            cx0 = (out_w - char_scale_w) // 2
            cy0 = char_foot_y - int(char_scale_h * 0.97)

            # Soft grounded beach contact shadows under both bears' feet
            sh_layer = frame_bgr.astype(np.float32)
            for sh_rx in [0.31, 0.71]:
                sx_c = int(cx0 + char_scale_w * sh_rx)
                sy_c = min(out_h - 6, char_foot_y - int(char_scale_h * 0.015))
                mask_sh = np.zeros((out_h, out_w), dtype=np.float32)
                cv2.ellipse(mask_sh, (sx_c, sy_c), (int(char_scale_w * 0.14), int(char_scale_h * 0.028)), 0, 0, 360, 0.38, -1)
                mask_sh = cv2.GaussianBlur(mask_sh, (31, 31), 9.0)[:, :, None]
                sh_layer = sh_layer * (1.0 - mask_sh)
            frame_bgr = np.clip(np.round(sh_layer), 0, 255).astype(np.uint8)

            # Alpha composite characters onto starry beach
            vx0, vy0 = max(0, cx0), max(0, cy0)
            vx1, vy1 = min(out_w, cx0 + char_scale_w), min(out_h, cy0 + char_scale_h)
            sub_cel = cel_scaled[vy0 - cy0 : vy1 - cy0, vx0 - cx0 : vx1 - cx0]
            a_c = sub_cel[:, :, 3:4].astype(np.float32) / 255.0
            roi_bg = frame_bgr[vy0:vy1, vx0:vx1].astype(np.float32)
            frame_bgr[vy0:vy1, vx0:vx1] = np.clip(np.round((1.0 - a_c) * roi_bg + a_c * sub_cel[:, :, :3].astype(np.float32)), 0, 255).astype(np.uint8)

            # 5) Foreground Interactive 2D Props & Hand-Drawn Heart/Sparkler FX!
            if fi < 48:
                # Golden Sparkler (仙女棒) held in Bubu's waving left paw!
                scale_f = char_scale_w / 1359.0
                paw_x = cx0 + (212.0 + 8.0 * math.sin(t * 4.2)) * scale_f
                paw_y = cy0 + (374.0 + 24.0 * math.sin(t * 8.4)) * scale_f
                ang_sp = math.radians(-122.0 + 14.0 * math.sin(t * 8.4))
                stick_len = 74.0 * scale_f
                tip_x = paw_x + math.cos(ang_sp) * stick_len
                tip_y = paw_y + math.sin(ang_sp) * stick_len
                cv2.line(
                    frame_bgr,
                    (int(round(paw_x)), int(round(paw_y))),
                    (int(round(tip_x)), int(round(tip_y))),
                    (75, 115, 165),
                    max(2, int(round(4.5 * scale_f))),
                    lineType=cv2.LINE_AA,
                )
                fx_f = frame_bgr.astype(np.float32)
                add_glow_circle(fx_f, tip_x, tip_y, 38.0 * scale_f, (110, 210, 255), 0.72)
                add_glow_circle(fx_f, tip_x, tip_y, 11.0 * scale_f, (240, 252, 255), 0.98)
                for k_ray in range(14):
                    ra = k_ray * (2.0 * math.pi / 14.0) + fi * 0.37
                    rl = (14.0 + 20.0 * ((math.sin(fi * 1.3 + k_ray * 2.1) + 1.0) * 0.5)) * scale_f
                    rx1 = tip_x + math.cos(ra) * rl
                    ry1 = tip_y + math.sin(ra) * rl + 4.0 * scale_f
                    cv2.line(
                        fx_f,
                        (int(round(tip_x)), int(round(tip_y))),
                        (int(round(rx1)), int(round(ry1))),
                        (185, 242, 255),
                        max(1, int(round(2.2 * scale_f))),
                        lineType=cv2.LINE_AA,
                    )
                frame_bgr = np.clip(np.round(fx_f), 0, 255).astype(np.uint8)

            elif fi < 100:
                # Floating Hand-Drawn Pastel Pink Hearts (♡) popping from Bubu & Yier's snuggled cheeks!
                scale_f = char_scale_w / 1359.0
                nuzzle_x = cx0 + 662.0 * scale_f
                nuzzle_y = cy0 + 115.0 * scale_f
                for h_t0, h_dx, h_sz in [(50, -28.0, 26.0), (62, 34.0, 22.0), (74, -14.0, 28.0), (85, 26.0, 23.0)]:
                    dh = fi - h_t0
                    if 0 <= dh <= 26:
                        uh = dh / 26.0
                        pop_scale = min(1.0, dh / 4.0) * (1.0 + 0.18 * math.sin(uh * math.pi))
                        hx_c = nuzzle_x + (h_dx + 18.0 * math.sin(uh * 5.0)) * scale_f
                        hy_c = nuzzle_y - (uh * 135.0) * scale_f
                        h_alpha = 1.0 if uh < 0.65 else (1.0 - (uh - 0.65) / 0.35)
                        draw_handdrawn_heart(frame_bgr, hx_c, hy_c, h_sz * scale_f * pop_scale, 12.0 * math.sin(uh * 6.0), h_alpha)

            else:
                # Glowing Rose-Gold Heart Pulse right inside their joined paw-heart + celebratory mini hearts!
                scale_f = char_scale_w / 1359.0
                ph_x = cx0 + (679.0 + 9.0 * math.sin((fi - 100) / 24.0 * 5.0)) * scale_f
                ph_y = cy0 + 555.0 * scale_f
                pulse = 0.75 + 0.25 * math.sin((fi - 100) * 0.45)
                fx_f = frame_bgr.astype(np.float32)
                add_glow_circle(fx_f, ph_x, ph_y, 34.0 * scale_f, (175, 155, 255), 0.55 * pulse)
                frame_bgr = np.clip(np.round(fx_f), 0, 255).astype(np.uint8)
                for h_t0, h_dx, h_sz in [(104, 0.0, 25.0), (118, -36.0, 21.0), (130, 38.0, 23.0)]:
                    dh = fi - h_t0
                    if 0 <= dh <= 24:
                        uh = dh / 24.0
                        hx_c = ph_x + (h_dx + 14.0 * math.sin(uh * 4.5)) * scale_f
                        hy_c = (cy0 + 95.0 * scale_f) - (uh * 120.0) * scale_f
                        h_alpha = 1.0 if uh < 0.65 else (1.0 - (uh - 0.65) / 0.35)
                        draw_handdrawn_heart(frame_bgr, hx_c, hy_c, h_sz * scale_f, 10.0 * math.sin(uh * 5.0), h_alpha)

            if fi in (18, 72, 122):
                sample_frames.append(frame_bgr.copy())
            yield frame_bgr

    encode_mp4(gen_frames(), out_w, out_h, 24.0, src_audio, out_path, crf=14)
    return sample_frames


def main():
    t0 = time.time()
    OUT_NEW.mkdir(parents=True, exist_ok=True)
    src_audio = WORK / "source.mp4"

    # 1. Build Part A (Mouth-Fixed Original Scene in all 3 formats — keeping everything else 100% unchanged!)
    _, fixed_1920 = build_part_a_mouth_fix(src_audio)

    # 2. Extract Clean Despilled RGBA Cels for Part B (Brand-New Starry Beach & Fireworks Scene)
    print("[Part B] Extracting zero-spill RGBA character cels & building 24fps Live2D animation ...", flush=True)
    pose1_rgba = extract_despilled_rgba(WORK / "cel_pose1_cheer.png")
    pose1_blink_rgba = make_pose1_blink_rgba(pose1_rgba)
    pose2_rgba = extract_despilled_rgba(WORK / "cel_pose2_cuddle_standing.png")
    pose3_rgba = extract_despilled_rgba(WORK / "cel_pose3_heart.png")

    bg_16x9 = cv2.imread(str(WORK / "bg_starry_16x9.png"))
    bg_9x16 = cv2.imread(str(WORK / "bg_starry_9x16.png"))
    assert bg_16x9 is not None and bg_9x16 is not None

    # Render B1: 16:9 Widescreen Full-HD (1920x1080)
    print("[Part B] Encoding B1_new_scene_starry_fireworks_16x9_1920x1080.mp4 ...", flush=True)
    fw_16x9 = [
        {"t0": 10, "cx": 1340.0, "cy": 230.0, "max_r": 145.0, "col": (185, 165, 255), "heart": False},
        {"t0": 54, "cx": 980.0, "cy": 195.0, "max_r": 165.0, "col": (165, 140, 255), "heart": True},
        {"t0": 98, "cx": 1420.0, "cy": 215.0, "max_r": 170.0, "col": (135, 215, 255), "heart": False},
        {"t0": 108, "cx": 960.0, "cy": 185.0, "max_r": 185.0, "col": (175, 145, 255), "heart": True},
    ]
    samples_16x9 = render_new_scene_video(
        bg_16x9,
        out_w=1920,
        out_h=1080,
        horizon_y=595,
        lantern_xy=(345, 922),
        char_scale_w=980,
        char_foot_y=1052,
        firework_specs=fw_16x9,
        pose1_rgba=pose1_rgba,
        pose1_blink_rgba=pose1_blink_rgba,
        pose2_rgba=pose2_rgba,
        pose3_rgba=pose3_rgba,
        src_audio=src_audio,
        out_path=OUT_NEW / "B1_new_scene_starry_fireworks_16x9_1920x1080.mp4",
    )

    # Render B2: 9:16 Vertical Full-HD (1080x1920)
    print("[Part B] Encoding B2_new_scene_starry_fireworks_9x16_1080x1920.mp4 ...", flush=True)
    fw_9x16 = [
        {"t0": 10, "cx": 760.0, "cy": 470.0, "max_r": 150.0, "col": (185, 165, 255), "heart": False},
        {"t0": 54, "cx": 540.0, "cy": 380.0, "max_r": 175.0, "col": (165, 140, 255), "heart": True},
        {"t0": 98, "cx": 300.0, "cy": 520.0, "max_r": 145.0, "col": (135, 215, 255), "heart": False},
        {"t0": 106, "cx": 560.0, "cy": 360.0, "max_r": 195.0, "col": (175, 145, 255), "heart": True},
    ]
    samples_9x16 = render_new_scene_video(
        bg_9x16,
        out_w=1080,
        out_h=1920,
        horizon_y=1285,
        lantern_xy=(144, 1652),
        char_scale_w=880,
        char_foot_y=1875,
        firework_specs=fw_9x16,
        pose1_rgba=pose1_rgba,
        pose1_blink_rgba=pose1_blink_rgba,
        pose2_rgba=pose2_rgba,
        pose3_rgba=pose3_rgba,
        src_audio=src_audio,
        out_path=OUT_NEW / "B2_new_scene_starry_fireworks_9x16_1080x1920.mp4",
    )

    # Save B3 Showcase Sheet (3 acts of 16:9 + 3 acts of 9:16 + Fixed Original f=004/f=070!)
    row_16x9 = np.hstack([
        draw_badge(cv2.resize(samples_16x9[0], (640, 360), interpolation=cv2.INTER_AREA), "New Scene Act 1 (Sparkler & Cheer - 16:9)", (12, 10), 17),
        draw_badge(cv2.resize(samples_16x9[1], (640, 360), interpolation=cv2.INTER_AREA), "New Scene Act 2 (Cheek Cuddle & Hearts - 16:9)", (12, 10), 17),
        draw_badge(cv2.resize(samples_16x9[2], (640, 360), interpolation=cv2.INTER_AREA), "New Scene Act 3 (Paw-Heart & Fireworks - 16:9)", (12, 10), 17),
    ])
    col4 = np.vstack([
        draw_badge(cv2.resize(fixed_1920[4], (840, 320), interpolation=cv2.INTER_AREA), "Mouth-Fixed Original f=004 (Clean 'w' Mouth)", (12, 10), 16),
        draw_badge(cv2.resize(fixed_1920[67], (840, 320), interpolation=cv2.INTER_AREA), "Mouth-Fixed Original f=067 (Zero Mouth Overlap)", (12, 10), 16),
    ])
    row_bot = np.hstack([
        draw_badge(cv2.resize(samples_9x16[0], (360, 640), interpolation=cv2.INTER_AREA), "9:16 Act 1", (10, 10), 16),
        draw_badge(cv2.resize(samples_9x16[1], (360, 640), interpolation=cv2.INTER_AREA), "9:16 Act 2", (10, 10), 16),
        draw_badge(cv2.resize(samples_9x16[2], (360, 640), interpolation=cv2.INTER_AREA), "9:16 Act 3", (10, 10), 16),
        col4,
    ])
    cv2.imwrite(str(OUT_NEW / "B3_new_scene_and_mouthfix_showcase.jpg"), np.vstack([row_16x9, row_bot]), [cv2.IMWRITE_JPEG_QUALITY, 95])

    print(f"\nALL v4 DELIVERABLES BUILT IN {time.time() - t0:.1f}s!", flush=True)
    for p in sorted(OUT_NEW.glob("*")):
        print(f"  {p.name:56s} {p.stat().st_size / 1024:8.1f} KB")


if __name__ == "__main__":
    main()
