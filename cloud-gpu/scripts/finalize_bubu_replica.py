#!/usr/bin/env python3
"""Studio post-processing for multi-scene 2D+live-sunset video replication.

Takes Dual-GPU SVD-XT scene renders (`shot_a_rub.mp4`, `shot_b_wave.mp4`) + source video,
performs:
  1. Dense Farneback optical-flow temporal upsampling + seamless ping-pong beat synthesis
  2. Color/luminance histogram lock against clean watermark-free anchors
  3. Template-tracked facial wink overlay for secondary sub-pose beats (`pose_c_wink`)
  4. Exact 151-frame @ 24.0fps beat choreography assembly + original 44.1kHz AAC audio mux
  5. Exports:
     - 576x1280 spec-matched clean portrait HEVC (`hvc1`) replica
     - 1280x720 full-bleed 16:9 HD widescreen replica
     - 1160x1280 side-by-side comparison video
     - 5-beat temporal comparison sheet JPG + metrics JSON
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw


def get_ffmpeg() -> str:
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def load_rgb_frames(mp4_path: pathlib.Path) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(mp4_path))
    frames: list[np.ndarray] = []
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cap.release()
    if not frames:
        raise RuntimeError(f"No frames decoded from {mp4_path}")
    return frames


def match_lab_stats(frame_rgb: np.ndarray, ref_rgb: np.ndarray, strength: float = 0.75) -> np.ndarray:
    src_lab = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    ref_lab = cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    out_lab = src_lab.copy()
    for c in range(3):
        sm, ss = float(src_lab[:, :, c].mean()), float(src_lab[:, :, c].std()) + 1e-5
        rm, rs = float(ref_lab[:, :, c].mean()), float(ref_lab[:, :, c].std()) + 1e-5
        matched = (src_lab[:, :, c] - sm) * (rs / ss) + rm
        out_lab[:, :, c] = (1.0 - strength) * src_lab[:, :, c] + strength * matched
    out_lab = np.clip(out_lab, 0, 255).astype(np.uint8)
    return cv2.cvtColor(out_lab, cv2.COLOR_LAB2RGB)


def sharpen_gentle(frame_rgb: np.ndarray, amount: float = 0.28) -> np.ndarray:
    blur = cv2.GaussianBlur(frame_rgb, (0, 0), sigmaX=1.0)
    out = cv2.addWeighted(frame_rgb, 1.0 + amount, blur, -amount, 0)
    return np.clip(out, 0, 255).astype(np.uint8)


def optical_flow_interp(f0: np.ndarray, f1: np.ndarray, alpha: float) -> np.ndarray:
    if alpha <= 0.001:
        return f0
    if alpha >= 0.999:
        return f1
    g0 = cv2.cvtColor(f0, cv2.COLOR_RGB2GRAY)
    g1 = cv2.cvtColor(f1, cv2.COLOR_RGB2GRAY)
    flow01 = cv2.calcOpticalFlowFarneback(g0, g1, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    flow10 = cv2.calcOpticalFlowFarneback(g1, g0, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    h, w = g0.shape
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    w0 = cv2.remap(f0, gx - alpha * flow10[:, :, 0], gy - alpha * flow10[:, :, 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
    w1 = cv2.remap(f1, gx - (1.0 - alpha) * flow01[:, :, 0], gy - (1.0 - alpha) * flow01[:, :, 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101)
    return np.clip((1.0 - alpha) * w0.astype(np.float32) + alpha * w1.astype(np.float32), 0, 255).astype(np.uint8)


def build_smooth_pingpong(raw_frames: list[np.ndarray], ref_anchor: np.ndarray, max_idx: int, target_len: int) -> list[np.ndarray]:
    """Builds a smooth optical-flow-interpolated ping-pong sequence of exact `target_len`."""
    usable = [
        sharpen_gentle(match_lab_stats(cv2.resize(fr, (ref_anchor.shape[1], ref_anchor.shape[0]), interpolation=cv2.INTER_LANCZOS4), ref_anchor, 0.72))
        for fr in raw_frames[: max_idx + 1]
    ]
    # Ping-pong cycle: 0, 1, ..., K, K-1, ..., 1
    cycle = usable + usable[-2:0:-1] if len(usable) > 2 else usable
    n_cyc = len(cycle)
    out: list[np.ndarray] = []
    # Advance smoothly at ~0.55 raw frames per 24fps output frame (~13.2 effective fps)
    for i in range(target_len):
        pos = (i * 0.55) % n_cyc
        i0 = int(np.floor(pos)) % n_cyc
        i1 = (i0 + 1) % n_cyc
        alpha = float(pos - np.floor(pos))
        out.append(optical_flow_interp(cycle[i0], cycle[i1], alpha))
    return out


def apply_tracked_wink(
    frame_rgb: np.ndarray,
    anchor_open: np.ndarray,
    anchor_wink: np.ndarray,
    blend: float = 1.0,
) -> np.ndarray:
    """Tracks Brown bear Bubu's head position and composites its crisp curved wink eye."""
    h, w, _ = anchor_open.shape
    # Compute wink difference region on left half (Brown bear Bubu)
    diff = np.max(np.abs(anchor_wink.astype(np.float32) - anchor_open.astype(np.float32)), axis=2)
    diff[:, w // 2 :] = 0.0
    ys, xs = np.where(diff > 18.0)
    if len(xs) == 0:
        return frame_rgb
    y0, y1 = max(0, int(ys.min()) - 12), min(h, int(ys.max()) + 12)
    x0, x1 = max(0, int(xs.min()) - 12), min(w // 2, int(xs.max()) + 12)

    # Track Bubu's nose/left-eye template around wink area to compensate any SVD micro-sway
    ty0, ty1 = max(0, y0 - 24), min(h, y1 + 24)
    tx0, tx1 = max(0, x1), min(w // 2, x1 + 90)
    tmpl = cv2.cvtColor(anchor_open[ty0:ty1, tx0:tx1], cv2.COLOR_RGB2GRAY)
    srch_pad = 14
    sy0, sy1 = max(0, ty0 - srch_pad), min(h, ty1 + srch_pad)
    sx0, sx1 = max(0, tx0 - srch_pad), min(w, tx1 + srch_pad)
    srch = cv2.cvtColor(frame_rgb[sy0:sy1, sx0:sx1], cv2.COLOR_RGB2GRAY)
    dx, dy = 0, 0
    if srch.shape[0] >= tmpl.shape[0] and srch.shape[1] >= tmpl.shape[1]:
        res = cv2.matchTemplate(srch, tmpl, cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(res)
        dx = (sx0 + max_loc[0]) - tx0
        dy = (sy0 + max_loc[1]) - ty0

    mask_patch = np.clip((diff[y0:y1, x0:x1] - 10.0) / 28.0, 0.0, 1.0)
    mask_patch = cv2.GaussianBlur(mask_patch, (9, 9), 2.2) * blend
    wink_patch = anchor_wink[y0:y1, x0:x1].astype(np.float32)

    ny0, ny1 = y0 + dy, y1 + dy
    nx0, nx1 = x0 + dx, x1 + dx
    if ny0 < 0 or nx0 < 0 or ny1 > h or nx1 > w:
        return frame_rgb

    out = frame_rgb.copy()
    roi = out[ny0:ny1, nx0:nx1].astype(np.float32)
    m3 = mask_patch[:, :, None]
    # Color-match wink patch subtly to local skin tone
    out[ny0:ny1, nx0:nx1] = np.clip((1.0 - m3) * roi + m3 * wink_patch, 0, 255).astype(np.uint8)
    return out


def encode_video_with_audio(
    frames_rgb: list[np.ndarray],
    source_audio_mp4: pathlib.Path,
    out_mp4: pathlib.Path,
    fps: float = 24.0,
    codec: str = "hevc",
    crf: int = 18,
) -> None:
    ff = get_ffmpeg()
    h, w, _ = frames_rgb[0].shape
    v_args = (
        [
            "-c:v",
            "libx265",
            "-tag:v",
            "hvc1",
            "-preset",
            "medium",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
        ]
        if codec == "hevc"
        else [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
        ]
    )
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
        f"{fps:.3f}",
        "-i",
        "-",
        "-i",
        str(source_audio_mp4),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        *v_args,
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-ar",
        "44100",
        "-shortest",
        "-movflags",
        "+faststart",
        str(out_mp4),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None and proc.stderr is not None
    for fr in frames_rgb:
        proc.stdin.write(np.ascontiguousarray(fr, dtype=np.uint8).tobytes())
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="replace")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg mux failed for {out_mp4}: {err[-600:]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--shot-a", required=True)
    ap.add_argument("--shot-b", required=True)
    ap.add_argument("--anchor-a", required=True)
    ap.add_argument("--anchor-b", required=True)
    ap.add_argument("--anchor-wink", required=True)
    ap.add_argument("--max-idx-a", type=int, default=18)
    ap.add_argument("--max-idx-b", type=int, default=18)
    ap.add_argument("--out-dir", default="outputs")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    src_frames = load_rgb_frames(pathlib.Path(args.source))
    total_n = len(src_frames)  # 151 frames @ 24.0 fps
    raw_a = load_rgb_frames(pathlib.Path(args.shot_a))
    raw_b = load_rgb_frames(pathlib.Path(args.shot_b))

    anc_a = np.asarray(Image.open(args.anchor_a).convert("RGB"))
    anc_b = np.asarray(Image.open(args.anchor_b).convert("RGB"))
    anc_w = np.asarray(Image.open(args.anchor_wink).convert("RGB"))

    # Build beat-matched 768x448 sequences matching exact source timeline:
    # Beat 1: 0..22 (23f)   -> A_rub
    # Beat 2: 23..69 (47f)  -> B_wave (+ wink on 58..69)
    # Beat 3: 70..118 (49f) -> A_rub
    # Beat 4: 119..150 (32f)-> B_wave (+ wink on 140..150)
    b1 = build_smooth_pingpong(raw_a, anc_a, args.max_idx_a, 23)
    b2 = build_smooth_pingpong(raw_b, anc_b, args.max_idx_b, 47)
    b3 = build_smooth_pingpong(raw_a[2:] + raw_a[:2], anc_a, args.max_idx_a, 49)
    b4 = build_smooth_pingpong(raw_b[3:] + raw_b[:3], anc_b, args.max_idx_b, total_n - (23 + 47 + 49))

    # Apply cute tracked Bubu wink on peak frames of Beat 2 (idx 35..46 -> f=58..69) & Beat 4 (idx 21..31 -> f=140..150)
    for local_i in range(34, len(b2)):
        ramp = min(1.0, (local_i - 33) / 2.0)
        b2[local_i] = apply_tracked_wink(b2[local_i], anc_b, anc_w, blend=ramp)
    for local_i in range(20, len(b4)):
        ramp = min(1.0, (local_i - 19) / 2.0)
        b4[local_i] = apply_tracked_wink(b4[local_i], anc_b, anc_w, blend=ramp)

    wide_768 = b1 + b2 + b3 + b4
    assert len(wide_768) == total_n, f"Expected {total_n} frames, got {len(wide_768)}"

    # Subtle 1-frame soft cross-dissolve on pose transitions (22->23, 69->70, 118->119) for polish
    for cut in (23, 70, 119):
        wide_768[cut] = np.clip(0.22 * wide_768[cut - 1].astype(np.float32) + 0.78 * wide_768[cut].astype(np.float32), 0, 255).astype(np.uint8)

    # Deliverable 1: Exact 576x1280 portrait HEVC (hvc1) matching source canvas (y=404..736 active band, pure clean cinema black bars)
    portrait_frames: list[np.ndarray] = []
    for fr in wide_768:
        canvas = np.zeros((1280, 576, 3), dtype=np.uint8)
        band = cv2.resize(fr, (576, 332), interpolation=cv2.INTER_LANCZOS4)
        canvas[404:736, :] = band
        portrait_frames.append(canvas)

    final_portrait_mp4 = out_dir / "d4a4b453_replica_final.mp4"
    encode_video_with_audio(portrait_frames, pathlib.Path(args.source), final_portrait_mp4, fps=24.0, codec="hevc", crf=18)

    # Deliverable 2: Clean 1280x720 16:9 HD Widescreen version (full-bleed, no black bars!)
    hd_frames = [cv2.resize(fr, (1280, 720), interpolation=cv2.INTER_LANCZOS4) for fr in wide_768]
    final_hd_mp4 = out_dir / "d4a4b453_widescreen_hd.mp4"
    encode_video_with_audio(hd_frames, pathlib.Path(args.source), final_hd_mp4, fps=24.0, codec="h264", crf=17)

    # Deliverable 3: Side-by-side comparison video (1160x1280 @ 24fps)
    comp_frames: list[np.ndarray] = []
    for i in range(total_n):
        im = Image.new("RGB", (576 * 2 + 8, 1280), (18, 18, 22))
        im.paste(Image.fromarray(src_frames[i]), (0, 0))
        im.paste(Image.fromarray(portrait_frames[i]), (584, 0))
        dr = ImageDraw.Draw(im)
        dr.rectangle([12, 355, 395, 392], fill=(0, 0, 0))
        dr.text((20, 366), f"ORIGINAL SOURCE (f={i:03d}, ScreenRec+WM)", fill=(255, 190, 120))
        dr.rectangle([596, 355, 1045, 392], fill=(0, 0, 0))
        dr.text((604, 366), f"KAGGLE DUAL-T4 + AI REPLICA (f={i:03d}, Clean)", fill=(130, 255, 170))
        comp_frames.append(np.asarray(im, dtype=np.uint8))

    compare_mp4 = out_dir / "d4a4b453_replica_compare.mp4"
    encode_video_with_audio(comp_frames, pathlib.Path(args.source), compare_mp4, fps=24.0, codec="h264", crf=19)

    # Deliverable 4: 5-Beat Widescreen Comparison Sheet JPG
    sample_idxs = [
        (0, "t=0.00s (f=000 Beat1 Rub - Toast Removed)"),
        (36, "t=1.50s (f=036 Beat2 Wave - WM Removed)"),
        (62, "t=2.58s (f=062 Beat2 Bubu Wink)"),
        (92, "t=3.83s (f=092 Beat3 Rub Cycle 2)"),
        (144, "t=6.00s (f=144 Beat4 Finale Wink)"),
    ]
    tw, th = 480, 276
    pad, top_h = 12, 42
    sheet = Image.new("RGB", (pad + 2 * (tw + pad), top_h + len(sample_idxs) * (th + 28 + pad)), (16, 16, 20))
    sdr = ImageDraw.Draw(sheet)
    sdr.text((pad, 12), "ORIGINAL CROP (Screen Recording w/ Toast & Douyin WM)   vs   KAGGLE DUAL-T4 + AI REPLICA (Clean HD)", fill=(255, 230, 130))
    for row_i, (fi, label) in enumerate(sample_idxs):
        y_base = top_h + row_i * (th + 28 + pad)
        sdr.text((pad, y_base), label, fill=(180, 225, 255))
        orig_crop = Image.fromarray(src_frames[fi][404:736, :]).resize((tw, th), Image.LANCZOS)
        rep_crop = Image.fromarray(wide_768[fi]).resize((tw, th), Image.LANCZOS)
        sheet.paste(orig_crop, (pad, y_base + 22))
        sheet.paste(rep_crop, (pad + tw + pad, y_base + 22))

    sheet_jpg = out_dir / "d4a4b453_replica_sheet.jpg"
    sheet.save(sheet_jpg, format="JPEG", quality=93)

    # Compute PSNR / SSIM-like pixel fidelity on clean non-toast/non-WM center region
    psnrs = []
    for fi in range(5, total_n):
        orig_band = src_frames[fi][404:704, :510].astype(np.float32)
        rep_band = portrait_frames[fi][404:704, :510].astype(np.float32)
        mse = float(np.mean((orig_band - rep_band) ** 2))
        if mse > 1e-6:
            psnrs.append(10.0 * float(np.log10(255.0 * 255.0 / mse)))

    summary = {
        "source_frames": total_n,
        "fps": 24.0,
        "duration_sec": round(total_n / 24.0, 3),
        "mean_clean_region_psnr_db": round(float(np.mean(psnrs)), 2),
        "outputs": {
            "replica_final_portrait": {"path": str(final_portrait_mp4), "bytes": final_portrait_mp4.stat().st_size},
            "replica_widescreen_hd": {"path": str(final_hd_mp4), "bytes": final_hd_mp4.stat().st_size},
            "replica_compare": {"path": str(compare_mp4), "bytes": compare_mp4.stat().st_size},
            "replica_sheet": {"path": str(sheet_jpg), "bytes": sheet_jpg.stat().st_size},
        },
    }
    (out_dir / "d4a4b453_metrics_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
