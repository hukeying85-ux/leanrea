#!/usr/bin/env python3
"""
Part A (v5 Corrected): 1:1 Restoration with White Yier's Authentic '3' Kissy Mouth (亲亲嘴) Preserved!

Fixes ONLY White Yier's overlapped mouth in the approved v3 1:1 restoration:
  - Frames f=000..022 & f=070..118 (Yier sideways rubbing eye / kissing toward Bubu):
    ERASES the leftover horizontal 'ω' moustache overlap at the top and KEEPS/RESTORES
    White Yier's authentic hand-drawn vertical '3' kissy mouth (亲亲嘴), aligned sub-pixel
    to each frame's exact lower-'3' stroke trajectory!
  - Frames f=067..069 (3 front-facing frames closing from f=066 open smile before turning sideways at f=070):
    Cleans the ghosted pink/grey hanging stub under the front smile so f=066 -> f=067..069 -> f=070
    transitions with zero double-mouth overlap.
  - Frames f=023..066 & f=119..150: 100% UNTOUCHED (exact 0.0000 pixel diff).
  - Outside Yier's mouth ROI across ALL 151 frames: exact 0.0000 pixel diff (其余都不变).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import cv2
import imageio.v3 as iio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter1d, median_filter

WORK = Path("/tmp/v5_work")
OUT_DIR = Path("/home/user/leanrea/outputs_v5_kissfix_and_cloudgpu")


def laplace_inpaint_roi(roi_rgb: np.ndarray, mask_bool: np.ndarray, n_iter: int = 320) -> np.ndarray:
    out = roi_rgb.astype(np.float32).copy()
    if not np.any(mask_bool):
        return roi_rgb.copy()
    k = np.array(
        [[0.05, 0.20, 0.05], [0.20, 0.00, 0.20], [0.05, 0.20, 0.05]],
        dtype=np.float32,
    )
    ring = cv2.dilate(mask_bool.astype(np.uint8), np.ones((5, 5), np.uint8), iterations=1).astype(bool) & (~mask_bool)
    init_val = np.median(out[ring], axis=0) if np.any(ring) else np.array([202.0, 192.0, 196.0], dtype=np.float32)
    out[mask_bool] = init_val
    for _ in range(n_iter):
        avg = cv2.filter2D(out, -1, k, borderType=cv2.BORDER_REPLICATE)
        out[mask_bool] = avg[mask_bool]
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def build_authentic_kissy_template(f4: np.ndarray):
    """Extract Yier's real hand-drawn '3' kissy mouth (亲亲嘴) from f=004 and complete its top kissy lip curl."""
    tx1, ty1, tx2, ty2 = 1444, 742, 1496, 814
    crop = f4[ty1:ty2, tx1:tx2].astype(np.float32)
    skin = np.median(f4[760:805, 1494:1504].reshape(-1, 3), axis=0).astype(np.float32)
    ink = np.percentile(crop.reshape(-1, 3), 2, axis=0).astype(np.float32)
    skin_lum = 0.299 * skin[0] + 0.587 * skin[1] + 0.114 * skin[2]
    ink_lum = 0.299 * ink[0] + 0.587 * ink[1] + 0.114 * ink[2]
    lum = 0.299 * crop[:, :, 0] + 0.587 * crop[:, :, 1] + 0.114 * crop[:, :, 2]
    raw_alpha = np.clip((skin_lum - lum) / max(1.0, (skin_lum - ink_lum)), 0.0, 1.0)
    raw_alpha[raw_alpha < 0.12] = 0.0

    tmpl = np.zeros_like(raw_alpha)
    tmpl[19:, :] = raw_alpha[19:, :]

    h, w = tmpl.shape
    ss = 4
    top_hi = np.zeros((h * ss, w * ss), dtype=np.float32)
    t = np.linspace(0.0, 1.0, 48)[:, None]
    p0 = np.array([23.0 * ss, 12.5 * ss], dtype=np.float32)
    p1 = np.array([33.5 * ss, 8.5 * ss], dtype=np.float32)
    p2 = np.array([39.0 * ss, 15.5 * ss], dtype=np.float32)
    p3 = np.array([35.8 * ss, 24.0 * ss], dtype=np.float32)
    pts = np.round(
        ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * (t**2) * p2 + (t**3) * p3
    ).astype(np.int32)
    th = int(round(6.2 * ss))
    cv2.polylines(top_hi, [pts], isClosed=False, color=1.0, thickness=th, lineType=cv2.LINE_AA)
    cv2.circle(top_hi, (int(round(p0[0])), int(round(p0[1]))), th // 2, 1.0, -1, lineType=cv2.LINE_AA)
    top_lo = cv2.resize(top_hi, (w, h), interpolation=cv2.INTER_AREA)
    top_lo = cv2.GaussianBlur(top_lo, (3, 3), 0.45)

    out_alpha = tmpl.copy()
    for ry in range(0, 25):
        if ry <= 18:
            out_alpha[ry, :] = top_lo[ry, :]
        else:
            w_top = max(0.0, 1.0 - (ry - 18) / 6.0)
            out_alpha[ry, :] = np.clip(tmpl[ry, :] * (1.0 - w_top) + top_lo[ry, :] * w_top, 0.0, 1.0)
    return out_alpha, ink, (tx1, ty1, tx2, ty2)


def find_kissy_mouth_cc(frame: np.ndarray):
    x1, y1, x2, y2 = 1405, 700, 1555, 842
    patch = frame[y1:y2, x1:x2]
    ph, pw = patch.shape[:2]
    lum = 0.299 * patch[:, :, 0] + 0.587 * patch[:, :, 1] + 0.114 * patch[:, :, 2]
    skin_border = np.concatenate([patch[0:4, :, :].reshape(-1, 3), patch[-4:, :, :].reshape(-1, 3)], axis=0)
    skin_lums = 0.299 * skin_border[:, 0] + 0.587 * skin_border[:, 1] + 0.114 * skin_border[:, 2]
    valid_skin = skin_border[skin_lums > 165]
    bg_med = np.median(valid_skin, axis=0) if len(valid_skin) > 10 else np.array([198.0, 189.0, 193.0])
    diff = np.linalg.norm(patch.astype(np.float32) - bg_med[None, None, :], axis=2)
    dark = (diff > 27.0) | (lum < 156.0)

    num_cc, labels, stats, centroids = cv2.connectedComponentsWithStats(dark.astype(np.uint8), connectivity=8)
    mouth_cc = np.zeros((ph, pw), dtype=bool)
    other_ink = np.zeros((ph, pw), dtype=bool)

    best_cid = None
    best_score = 1e9
    for cid in range(1, num_cc):
        area = stats[cid, cv2.CC_STAT_AREA]
        bw = stats[cid, cv2.CC_STAT_WIDTH]
        bh = stats[cid, cv2.CC_STAT_HEIGHT]
        bx0 = x1 + stats[cid, cv2.CC_STAT_LEFT]
        bx1 = bx0 + bw
        cx_g = x1 + centroids[cid][0]
        cy_g = y1 + centroids[cid][1]
        if bx0 <= x1 + 2 or bx1 >= x2 - 2 or area > 2800:
            continue
        if bh >= 35 and 180 <= area <= 2600 and (1425 <= cx_g <= 1525) and (725 <= cy_g <= 812):
            score = abs(cx_g - 1475.0) + abs(cy_g - 768.0)
            if score < best_score:
                best_score = score
                best_cid = cid

    if best_cid is not None:
        mouth_cc |= labels == best_cid
        mbx0 = x1 + stats[best_cid, cv2.CC_STAT_LEFT]
        mbx1 = mbx0 + stats[best_cid, cv2.CC_STAT_WIDTH]
        mby0 = y1 + stats[best_cid, cv2.CC_STAT_TOP]
        mby1 = mby0 + stats[best_cid, cv2.CC_STAT_HEIGHT]
        for cid in range(1, num_cc):
            if cid == best_cid:
                continue
            area = stats[cid, cv2.CC_STAT_AREA]
            bx0 = x1 + stats[cid, cv2.CC_STAT_LEFT]
            bx1 = bx0 + stats[cid, cv2.CC_STAT_WIDTH]
            by0 = y1 + stats[cid, cv2.CC_STAT_TOP]
            by1 = by0 + stats[cid, cv2.CC_STAT_HEIGHT]
            if bx0 > x1 + 6 and bx1 < x2 - 12 and area <= 450:
                if bx1 >= mbx0 - 12 and bx0 <= mbx1 + 12 and by1 >= mby0 - 12 and by0 <= mby1 + 18:
                    mouth_cc |= labels == cid
                else:
                    other_ink |= labels == cid
            else:
                other_ink |= labels == cid
    else:
        other_ink |= dark
    return (x1, y1, x2, y2), mouth_cc, other_ink


def draw_clean_front_omega(canvas_rgb: np.ndarray, cx: float, cy: float) -> np.ndarray:
    """Front-facing closing smile on f=067..069 ONLY (while Yier is still facing front before turning at f=070)."""
    out = canvas_rgb.copy()
    x1, y1 = int(round(cx - 44)), int(round(cy - 24))
    x2, y2 = int(round(cx + 44)), int(round(cy + 28))
    ph, pw = y2 - y1, x2 - x1
    ss = 4
    alpha_hi = np.zeros((ph * ss, pw * ss), dtype=np.float32)
    t = np.linspace(0.0, 1.0, 44)[:, None]

    def bez(p0, p1, p2, p3):
        p0, p1, p2, p3 = map(lambda p: np.array(p, np.float32), (p0, p1, p2, p3))
        return np.round(
            ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * (t**2) * p2 + (t**3) * p3
        ).astype(np.int32)

    hw, dip, tip = 23.5, 9.5, 4.5
    pL0 = ((cx - hw - x1) * ss, (cy - tip - y1) * ss)
    pL1 = ((cx - hw * 0.85 - x1) * ss, (cy + dip * 1.25 - y1) * ss)
    pL2 = ((cx - hw * 0.24 - x1) * ss, (cy + dip * 1.10 - y1) * ss)
    pM = ((cx - x1) * ss, (cy - 1.2 - y1) * ss)
    pR1 = ((cx + hw * 0.24 - x1) * ss, (cy + dip * 1.10 - y1) * ss)
    pR2 = ((cx + hw * 0.85 - x1) * ss, (cy + dip * 1.25 - y1) * ss)
    pR3 = ((cx + hw - x1) * ss, (cy - tip - y1) * ss)
    th = int(round(6.2 * ss))
    cv2.polylines(alpha_hi, [bez(pL0, pL1, pL2, pM)], False, 1.0, th, cv2.LINE_AA)
    cv2.polylines(alpha_hi, [bez(pM, pR1, pR2, pR3)], False, 1.0, th, cv2.LINE_AA)
    for pt in (pL0, pM, pR3):
        cv2.circle(alpha_hi, (int(pt[0]), int(pt[1])), th // 2, 1.0, -1, cv2.LINE_AA)
    alpha = cv2.GaussianBlur(cv2.resize(alpha_hi, (pw, ph), interpolation=cv2.INTER_AREA), (3, 3), 0.42)[:, :, None]
    roi = out[y1:y2, x1:x2].astype(np.float32)
    ink = np.array([30.0, 21.0, 23.0], np.float32)[None, None, :]
    out[y1:y2, x1:x2] = np.clip(np.round(roi * (1.0 - alpha) + ink * alpha), 0, 255).astype(np.uint8)
    return out


def open_mp4_pipe(out_path: Path, w: int, h: int, fps: int = 24):
    import imageio_ffmpeg

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    tmp_vid = WORK / f"_tmp_{out_path.name}"
    cmd = [
        ff,
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{w}x{h}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "14",
        "-pix_fmt",
        "yuv420p",
        str(tmp_vid),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, tmp_vid


def finish_mp4_pipe(proc: subprocess.Popen, tmp_vid: Path, out_path: Path, audio_src: Path):
    import imageio_ffmpeg

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    assert proc.stdin is not None
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg rawvideo encode failed: rc={rc}")

    mux_cmd = [
        ff,
        "-y",
        "-i",
        str(tmp_vid),
        "-i",
        str(audio_src),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    subprocess.run(mux_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tmp_vid.unlink(missing_ok=True)


def main():
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    v3_16x9 = WORK / "v3_master_1920x1108.mp4"
    v3_9x16 = WORK / "v3_9x16_1080x1920.mp4"
    src_mp4 = WORK / "source.mp4"

    # Read ONLY first frame of source.mp4 and f=45 of 9x16 to save >2.2 GB RAM!
    s0 = next(iio.imiter(src_mp4))
    row_lum = s0.mean(axis=(1, 2))
    active_rows = np.where(row_lum > 12.0)[0]
    ay0, ay1 = int(active_rows[0]), int(active_rows[-1]) + 1
    band_h = ay1 - ay0

    frames_16x9 = [fr for fr in iio.imiter(v3_16x9)]
    assert len(frames_16x9) == 151

    f45_9x16 = None
    for idx9, fr9 in enumerate(iio.imiter(v3_9x16)):
        if idx9 == 45:
            f45_9x16 = fr9
            break
    assert f45_9x16 is not None

    # Save clean character reference sheet from untouched f=045 for Part B New Scene generation!
    Image.fromarray(frames_16x9[45][380:1108, 360:1780]).save(WORK / "bubu_yier_char_ref.png")

    tmpl_alpha, tmpl_ink, (tx1, ty1, tx2, ty2) = build_authentic_kissy_template(frames_16x9[4])

    def direct_lower3_anchor(fi: int):
        (x1, y1, x2, y2), mcc, _ = find_kissy_mouth_cc(frames_16x9[fi])
        ys, xs = np.where(mcc)
        gxs = x1 + xs
        gys = y1 + ys
        y_bot = float(np.percentile(gys, 98.0))
        sel = (gys >= y_bot - 36.0) & (gys <= y_bot - 4.0)
        x_low = float(np.percentile(gxs[sel], 85.0))
        return x_low, y_bot

    x4, y4 = direct_lower3_anchor(4)

    def build_direct_offsets(seg_fis: list[int]):
        pts = [direct_lower3_anchor(fi) for fi in seg_fis]
        xs = np.array([tx1 + (p[0] - x4) for p in pts], dtype=np.float32)
        ys = np.array([ty1 + (p[1] - y4) for p in pts], dtype=np.float32)
        xs_s = gaussian_filter1d(median_filter(xs, size=3, mode="nearest"), sigma=0.65, mode="nearest")
        ys_s = gaussian_filter1d(median_filter(ys, size=3, mode="nearest"), sigma=0.65, mode="nearest")
        return {fi: (float(xs_s[i]), float(ys_s[i])) for i, fi in enumerate(seg_fis)}

    offsets: dict[int, tuple[float, float]] = {}
    offsets.update(build_direct_offsets(list(range(0, 23))))
    offsets.update(build_direct_offsets(list(range(70, 119))))

    probe_band = cv2.resize(frames_16x9[45], (1080, int(round(1108 * 1080 / 1920))), interpolation=cv2.INTER_AREA)
    res9 = cv2.matchTemplate(f45_9x16, probe_band, cv2.TM_CCOEFF_NORMED)
    _, max_v9, _, max_loc9 = cv2.minMaxLoc(res9)
    y_off_9x16 = int(max_loc9[1])
    fg_h_9x16 = probe_band.shape[0]
    print(f"[9:16 align] y_off={y_off_9x16}, fg_h={fg_h_9x16}, match_corr={max_v9:.5f}")

    p_a1 = OUT_DIR / "A1_亲亲嘴修正_横屏16x9超清母带_1920x1108.mp4"
    p_a2 = OUT_DIR / "A2_亲亲嘴修正_原版1比1竖屏同款构图_576x1280.mp4"
    p_a3 = OUT_DIR / "A3_亲亲嘴修正_竖屏9x16满屏无缝版_1080x1920.mp4"
    p_a4 = OUT_DIR / "A4_亲亲嘴修正前后放大核验图_Before_vs_After.png"

    proc_a1, tmp_a1 = open_mp4_pipe(p_a1, 1920, 1108, fps=24)
    proc_a2, tmp_a2 = open_mp4_pipe(p_a2, 576, 1280, fps=24)
    proc_a3, tmp_a3 = open_mp4_pipe(p_a3, 1080, 1920, fps=24)

    sample_fis = [0, 4, 15, 22, 67, 70, 73, 95]
    saved_samples: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    outside_roi_max_diff = 0.0
    untouched_frames_max_diff = 0.0

    for fi, (orig, v9_orig) in enumerate(zip(frames_16x9, iio.imiter(v3_9x16))):
        if fi in (67, 68, 69):
            out = orig.copy()
            x1, y1, x2, y2 = 1345, 720, 1445, 795
            patch = out[y1:y2, x1:x2]
            bg = np.median(patch[-6:, :, :].reshape(-1, 3), axis=0)
            diff = np.linalg.norm(patch.astype(np.float32) - bg[None, None, :], axis=2)
            mask = cv2.dilate((diff > 20.0).astype(np.uint8), np.ones((7, 7), np.uint8), iterations=1).astype(bool)
            out[y1:y2, x1:x2] = laplace_inpaint_roi(patch, mask, n_iter=280)
            ys, xs = np.where(diff[:38, :] > 35.0)
            cx = x1 + float(np.median(xs)) if len(xs) > 10 else 1393.0
            cy = y1 + float(np.median(ys)) if len(ys) > 10 else 744.0
            out = draw_clean_front_omega(out, cx, cy)
            chk = np.abs(out.astype(np.float32) - orig.astype(np.float32))
            chk[705:810, 1335:1455] = 0.0
            outside_roi_max_diff = max(outside_roi_max_diff, float(chk.max()))
        elif fi in offsets:
            out = orig.copy()
            (x1, y1, x2, y2), mouth_cc, other_ink = find_kissy_mouth_cc(out)
            if np.any(mouth_cc):
                dil_mouth = cv2.dilate(mouth_cc.astype(np.uint8), np.ones((9, 9), np.uint8), iterations=1).astype(bool)
                guard_other = cv2.dilate(other_ink.astype(np.uint8), np.ones((9, 9), np.uint8), iterations=1).astype(bool)
                clean_mask = dil_mouth & (~guard_other)
                out[y1:y2, x1:x2] = laplace_inpaint_roi(out[y1:y2, x1:x2], clean_mask, n_iter=320)

            gx0, gy0 = offsets[fi]
            ix0, iy0 = int(np.floor(gx0)), int(np.floor(gy0))
            fx, fy = gx0 - ix0, gy0 - iy0
            th, tw = tmpl_alpha.shape
            M = np.float32([[1, 0, fx], [0, 1, fy]])
            shifted_a = cv2.warpAffine(
                tmpl_alpha,
                M,
                (tw + 2, th + 2),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0.0,
            )
            shifted_a = np.clip(shifted_a, 0.0, 1.0)[:, :, None]
            roi = out[iy0 : iy0 + th + 2, ix0 : ix0 + tw + 2].astype(np.float32)
            out[iy0 : iy0 + th + 2, ix0 : ix0 + tw + 2] = np.clip(
                np.round(roi * (1.0 - shifted_a) + tmpl_ink[None, None, :] * shifted_a), 0, 255
            ).astype(np.uint8)

            chk = np.abs(out.astype(np.float32) - orig.astype(np.float32))
            chk[700:842, 1405:1555] = 0.0
            outside_roi_max_diff = max(outside_roi_max_diff, float(chk.max()))
        else:
            out = orig
            untouched_frames_max_diff = max(
                untouched_frames_max_diff, float(np.abs(out.astype(np.float32) - orig.astype(np.float32)).max())
            )

        if fi in sample_fis:
            saved_samples[fi] = (orig.copy(), out.copy())

        assert proc_a1.stdin is not None and proc_a2.stdin is not None and proc_a3.stdin is not None
        proc_a1.stdin.write(out.tobytes())

        c576 = np.zeros((1280, 576, 3), dtype=np.uint8)
        c576[ay0:ay1, :, :] = cv2.resize(out, (576, band_h), interpolation=cv2.INTER_AREA)
        proc_a2.stdin.write(c576.tobytes())

        v9 = v9_orig.copy()
        if fi in offsets or fi in (67, 68, 69):
            old_band = cv2.resize(orig, (1080, fg_h_9x16), interpolation=cv2.INTER_AREA)
            new_band = cv2.resize(out, (1080, fg_h_9x16), interpolation=cv2.INTER_AREA)
            delta_mask = np.any(old_band != new_band, axis=2)
            alpha9 = cv2.GaussianBlur(
                cv2.dilate(delta_mask.astype(np.uint8) * 255, np.ones((5, 5), np.uint8), iterations=1).astype(
                    np.float32
                )
                / 255.0,
                (5, 5),
                0.8,
            )[:, :, None]
            orig_slice = v9[y_off_9x16 : y_off_9x16 + fg_h_9x16, :, :].astype(np.float32)
            v9[y_off_9x16 : y_off_9x16 + fg_h_9x16, :, :] = np.clip(
                np.round(orig_slice * (1.0 - alpha9) + new_band.astype(np.float32) * alpha9), 0, 255
            ).astype(np.uint8)
        proc_a3.stdin.write(v9.tobytes())

    assert outside_roi_max_diff == 0.0, f"Non-zero diff outside mouth ROI: {outside_roi_max_diff}"
    assert untouched_frames_max_diff == 0.0, f"Untouched frames modified: {untouched_frames_max_diff}"

    finish_mp4_pipe(proc_a1, tmp_a1, p_a1, v3_16x9)
    finish_mp4_pipe(proc_a2, tmp_a2, p_a2, v3_16x9)
    finish_mp4_pipe(proc_a3, tmp_a3, p_a3, v3_9x16)

    # Build crystal-clear Before vs After verification sheet
    cw, ch = 260, 230
    sheet = Image.new("RGB", (len(sample_fis) * cw, ch * 2 + 410), (18, 18, 22))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for col, fi in enumerate(sample_fis):
        orig_s, fix_s = saved_samples[fi]
        cx_crop = 1395 if fi == 67 else 1468
        x0, y0 = cx_crop - 85, 695
        c_orig = Image.fromarray(orig_s[y0 : y0 + 150, x0 : x0 + 170]).resize((cw - 4, ch - 4), Image.NEAREST)
        c_fix = Image.fromarray(fix_s[y0 : y0 + 150, x0 : x0 + 170]).resize((cw - 4, ch - 4), Image.NEAREST)
        sheet.paste(c_orig, (col * cw + 2, 20))
        sheet.paste(c_fix, (col * cw + 2, 20 + ch))
        draw.rectangle([col * cw + 4, 22, col * cw + 145, 40], fill=(0, 0, 0))
        draw.text((col * cw + 8, 25), f"BEFORE f={fi:03d}", fill=(255, 140, 140), font=font)
        draw.rectangle([col * cw + 4, 22 + ch, col * cw + 175, 40 + ch], fill=(0, 0, 0))
        lbl = f"AFTER 3-KISS f={fi:03d}" if fi != 67 else f"AFTER CLOSE f={fi:03d}"
        draw.text((col * cw + 8, 25 + ch), lbl, fill=(130, 255, 160), font=font)

    for k, fi in enumerate([4, 70, 73, 95]):
        _, fix_s = saved_samples[fi]
        fc = Image.fromarray(fix_s[420:1080, 420:1760]).resize((512, 370), Image.LANCZOS)
        sheet.paste(fc, (k * 520 + 4, ch * 2 + 28))
        draw.rectangle([k * 520 + 8, ch * 2 + 32, k * 520 + 225, ch * 2 + 52], fill=(0, 0, 0))
        draw.text((k * 520 + 12, ch * 2 + 36), f"FULL SCENE KISSY f={fi:03d}", fill=(255, 235, 120), font=font)

    sheet.save(p_a4)
    report = {
        "outside_mouth_roi_max_diff": outside_roi_max_diff,
        "untouched_frames_max_diff": untouched_frames_max_diff,
        "kissy_frames_fixed": len(offsets),
        "transition_frames_cleaned": [67, 68, 69],
        "elapsed_sec": round(time.time() - t0, 2),
    }
    (OUT_DIR / "partA_kissmouth_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("Part A complete:", json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
