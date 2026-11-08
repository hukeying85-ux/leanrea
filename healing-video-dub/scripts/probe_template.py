#!/usr/bin/env python3
"""
probe_template.py — 自动勘测任意短视频模板的帧率、静音/音效禁区与开口槽位，并导出嘴型核验条带图。
用法：
  python3 scripts/probe_template.py \
    --video templates/capybara_morning_10s/video_1080p24_muted.mp4 \
    --bgm templates/capybara_morning_10s/stems/bgm_and_kiss_sfx.flac \
    --out-strip examples/output/lip_strip.png
"""
import argparse
import json
import cv2
import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw


def detect_energy_windows(wav_path: str, win_sec: float = 0.05, thresh_rms: float = 0.025, min_gap_sec: float = 0.25):
    y, sr = sf.read(wav_path, dtype="float32")
    if y.ndim == 2:
        y = y.mean(axis=1)
    hop = max(1, int(sr * win_sec))
    active = []
    for i in range(0, len(y), hop):
        rms = float(np.sqrt(np.mean(y[i : i + hop] ** 2)))
        if rms >= thresh_rms:
            t0, t1 = i / sr, min(len(y) / sr, (i + hop) / sr)
            if active and (t0 - active[-1][1]) <= min_gap_sec:
                active[-1][1] = t1
            else:
                active.append([round(t0, 2), round(t1, 2)])
    return [w for w in active if (w[1] - w[0]) >= 0.35], round(len(y) / sr, 4), sr


def main():
    ap = argparse.ArgumentParser(description="勘测 3D 动画模板帧率、嘴型时间窗与音效峰值")
    ap.add_argument("--video", required=True, help="无水印模板视频 (.mp4)")
    ap.add_argument("--vocals", default="", help="可选：htdemucs 分离的原人声轨 (.flac/.wav)，用于自动切分槽位")
    ap.add_argument("--bgm", default="", help="可选：htdemucs 分离的伴奏+音效轨 (.flac/.wav)")
    ap.add_argument("--out-json", default="", help="输出测量结果 JSON")
    ap.add_argument("--out-strip", default="", help="输出每 0.5s 角色嘴部特写核验图 (.png)")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = []
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cap.release()

    grays = [cv2.cvtColor(cv2.resize(f, (180, 320)), cv2.COLOR_RGB2GRAY).astype(np.float32) for f in frames]
    diffs = [float(np.mean(np.abs(grays[i + 1] - grays[i]))) for i in range(len(grays) - 1)]
    frozen_pct = round(float(np.mean(np.array(diffs) < 0.35) * 100.0), 2) if diffs else 0.0

    report = {
        "resolution": [w, h],
        "fps": round(fps, 3),
        "frames": len(frames),
        "duration_sec": round(len(frames) / max(fps, 1e-6), 4),
        "frozen_frame_pct": frozen_pct,
        "a1_smooth_grade": "PASS" if frozen_pct < 3.0 else "WARN_STATIC_FRAMES",
    }

    if args.vocals:
        slots, dur_a, sr_a = detect_energy_windows(args.vocals)
        report["detected_vocal_slots"] = [{"start_sec": s, "end_sec": e, "dur_sec": round(e - s, 2)} for s, e in slots]
        report["audio_sr"] = sr_a

    if args.out_strip and frames:
        step_s = 0.5
        times = np.arange(0.5, min(10.0, len(frames) / fps), step_s)[:16]
        cw, ch = 320, 200
        cols = 4
        rows = int(np.ceil(len(times) / cols))
        grid = Image.new("RGB", (cw * cols, ch * rows), (20, 22, 28))
        draw = ImageDraw.Draw(grid)
        y0, y1 = int(h * 0.32), int(h * 0.66)
        x0, x1 = int(w * 0.05), int(w * 0.95)
        for idx, t in enumerate(times):
            fi = min(len(frames) - 1, int(round(t * fps)))
            crop = Image.fromarray(frames[fi][y0:y1, x0:x1]).resize((cw - 8, ch - 28), Image.Resampling.LANCZOS)
            gx, gy = (idx % cols) * cw, (idx // cols) * ch
            grid.paste(crop, (gx + 4, gy + 24))
            draw.text((gx + 8, gy + 5), f"t={t:.2f}s (f={fi})", fill=(255, 220, 110))
        grid.save(args.out_strip)
        report["lip_strip_png"] = args.out_strip

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
