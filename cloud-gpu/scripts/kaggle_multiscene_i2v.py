#!/usr/bin/env python3
"""Quota-Fast Dual-GPU Multi-Scene SVD-XT + Kaggle AI ($10/day) Pipeline.

Designed for multi-pose / multi-scene video replication within tight GPU quota budgets:
  1. Kaggle AI ($10/day Model Proxy) Pre-render VLM Director calibrates illustration-safe
     `(motion_bucket_id, noise_aug_strength)` per scene.
  2. Single shared download of `stabilityai/stable-video-diffusion-img2vid-xt` fp16 weights.
  3. Parallel Dual-T4 execution (`GPU-0` renders Scene A while `GPU-1` renders Scene B
     simultaneously in pure FP16 direct CUDA at 768x448, 18 steps -> ~2.3 min wall-clock).
  4. Kaggle AI ($10/day Model Proxy) Post-render VLM QA inspects rendered 5-frame strips.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from typing import Any


def ensure_deps() -> list[str]:
    for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "DIFFUSERS_OFFLINE"):
        os.environ[k] = "0"
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    needed = {
        "imageio_ffmpeg": "imageio-ffmpeg>=0.5",
        "diffusers": "diffusers>=0.30",
        "transformers": "transformers>=4.44",
        "accelerate": "accelerate>=0.30",
    }
    missing = [spec for mod, spec in needed.items() if importlib.util.find_spec(mod) is None]
    if missing:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--no-input", *missing])
    return missing


def find_ffmpeg() -> str:
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def encode_mp4(frames: list[Any], mp4_path: pathlib.Path, fps: int = 12) -> None:
    import numpy as np

    w, h = frames[0].size
    ff = find_ffmpeg()
    proc = subprocess.Popen(
        [
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
            "fast",
            "-crf",
            "15",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(mp4_path),
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None and proc.stderr is not None
    for fr in frames:
        proc.stdin.write(np.asarray(fr.convert("RGB"), dtype=np.uint8).tobytes())
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="replace")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed on {mp4_path}: {err[-400:]}")


def make_strip(frames: list[Any], out_path: pathlib.Path, label: str) -> None:
    from PIL import Image, ImageDraw

    idxs = [0, 6, 12, 18, min(24, len(frames) - 1)]
    thumbs = [frames[i].convert("RGB").resize((256, 150), Image.LANCZOS) for i in idxs]
    pad, head = 6, 26
    canvas = Image.new("RGB", (pad + 5 * (256 + pad), head + 150 + pad), (20, 20, 20))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 6), label, fill=(255, 225, 110))
    for i, im in enumerate(thumbs):
        canvas.paste(im, (pad + i * (256 + pad), head))
    canvas.save(out_path, format="JPEG", quality=92)


def _encode_b64(path: pathlib.Path, max_w: int = 1024) -> str:
    from PIL import Image

    im = Image.open(path).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, int(round(im.height * max_w / im.width))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def call_ai_proxy(prompt: str, images: list[pathlib.Path]) -> dict[str, Any]:
    base = os.environ.get("MODEL_PROXY_URL", "").strip().rstrip("/")
    key = os.environ.get("MODEL_PROXY_API_KEY", "").strip()
    if not base or not key:
        return {"ok": False, "reason": "no_proxy_env"}
    for sfx in ("/openapi", "/genai"):
        if base.endswith(sfx):
            base = base[: -len(sfx)]
            break
    endpoint = f"{base}/openapi/chat/completions"

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for p in images:
        if p.is_file():
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_encode_b64(p)}"}})

    models = [
        "google/gemini-2.5-flash",
        "google/gemini-3-flash-preview",
        "anthropic/claude-sonnet-5@default",
    ]
    errs = []
    for m in models:
        payload = json.dumps(
            {"model": m, "messages": [{"role": "user", "content": content}], "max_tokens": 2048}
        ).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "model": m, "text": body["choices"][0]["message"]["content"]}
        except Exception as exc:
            errs.append(f"{m}: {exc}")
    return {"ok": False, "reason": " | ".join(errs)[:400]}


def extract_json(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def worker_render(
    model_dir: str,
    scene_name: str,
    img_path: str,
    out_dir: str,
    width: int,
    height: int,
    steps: int,
    motion: int,
    noise: float,
    seed: int,
    log_json: str,
) -> int:
    import numpy as np
    import torch
    from diffusers import StableVideoDiffusionPipeline
    from PIL import Image

    t0 = time.time()
    pipe = StableVideoDiffusionPipeline.from_pretrained(
        model_dir, torch_dtype=torch.float16, variant="fp16", local_files_only=True
    ).to("cuda")
    cond = Image.open(img_path).convert("RGB").resize((width, height), Image.LANCZOS)
    gen = torch.Generator(device="cuda").manual_seed(seed)
    with torch.inference_mode():
        frames = pipe(
            cond,
            width=width,
            height=height,
            num_frames=25,
            num_inference_steps=steps,
            min_guidance_scale=1.0,
            max_guidance_scale=2.2,
            fps=12,
            motion_bucket_id=motion,
            noise_aug_strength=noise,
            decode_chunk_size=4,
            generator=gen,
        ).frames[0]

    out_p = pathlib.Path(out_dir)
    mp4_file = out_p / f"{scene_name}.mp4"
    strip_file = out_p / f"{scene_name}_strip.jpg"
    encode_mp4(frames, mp4_file, fps=12)
    make_strip(frames, strip_file, f"{scene_name} m={motion} n={noise} s={seed}")

    arrs = [np.asarray(f.convert("RGB"), dtype=np.float32) for f in frames]
    diffs = [float(np.mean(np.abs(arrs[i] - arrs[i - 1]))) for i in range(1, len(arrs))]
    meta = {
        "scene": scene_name,
        "gpu": os.environ.get("CUDA_VISIBLE_DEVICES", "0"),
        "width": width,
        "height": height,
        "steps": steps,
        "motion_bucket_id": motion,
        "noise_aug_strength": noise,
        "seed": seed,
        "elapsed_sec": round(time.time() - t0, 2),
        "mean_motion_mad": round(float(np.mean(diffs)), 3),
        "mp4": mp4_file.name,
        "strip": strip_file.name,
        "bytes": mp4_file.stat().st_size,
    }
    pathlib.Path(log_json).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[SVD GPU={meta['gpu']}] {scene_name} finished in {meta['elapsed_sec']}s (mad={meta['mean_motion_mad']})", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes-json", default="")
    ap.add_argument("--out-dir", default="/kaggle/working")
    ap.add_argument("--width", type=int, default=768)
    ap.add_argument("--height", type=int, default=448)
    ap.add_argument("--steps", type=int, default=18)
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--model-dir", default="")
    ap.add_argument("--scene-name", default="")
    ap.add_argument("--img-path", default="")
    ap.add_argument("--motion", type=int, default=52)
    ap.add_argument("--noise", type=float, default=0.012)
    ap.add_argument("--seed", type=int, default=20261126)
    ap.add_argument("--log-json", default="")
    args = ap.parse_args()

    if args.worker:
        return worker_render(
            args.model_dir,
            args.scene_name,
            args.img_path,
            args.out_dir,
            args.width,
            args.height,
            args.steps,
            args.motion,
            args.noise,
            args.seed,
            args.log_json,
        )

    t0 = time.time()
    installed = ensure_deps()
    import torch
    from huggingface_hub import snapshot_download

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required!")

    n_gpu = torch.cuda.device_count()
    gpu_names = [torch.cuda.get_device_name(i) for i in range(n_gpu)]
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenes = json.loads(args.scenes_json)
    scene_imgs = [pathlib.Path(s["image"]) for s in scenes]

    # Step 1: Kaggle AI ($10/day) Director calibration for cute 2D line-art illustration on sunset ocean
    ai_dir = call_ai_proxy(
        "These 2 keyframes are clean 2D cute bear illustrations on a real golden sunset beach. "
        "Calibrate SVD-XT parameters for subtle cute character breathing/arm sway + shimmering ocean waves "
        "WITHOUT warping cartoon faces/outlines. Return ONLY JSON: "
        "{\"scene_a\": {\"motion\": int 44..62, \"noise\": float 0.010..0.016}, "
        "\"scene_b\": {\"motion\": int 44..62, \"noise\": float 0.010..0.016}}",
        scene_imgs,
    )
    parsed_dir = extract_json(ai_dir.get("text", "")) if ai_dir.get("ok") else None
    for idx, sc in enumerate(scenes):
        key = "scene_a" if idx == 0 else "scene_b"
        if parsed_dir and isinstance(parsed_dir.get(key), dict):
            sc["motion"] = max(42, min(65, int(parsed_dir[key].get("motion", sc["motion"]))))
            sc["noise"] = round(max(0.008, min(0.018, float(parsed_dir[key].get("noise", sc["noise"])))), 4)

    # Step 2: Single shared fp16 download
    dl_t0 = time.time()
    model_dir = snapshot_download(
        repo_id="stabilityai/stable-video-diffusion-img2vid-xt",
        local_dir="/tmp/hf_svd_multi",
        allow_patterns=["*.json", "*.txt", "*fp16*.safetensors"],
    )
    dl_sec = round(time.time() - dl_t0, 2)
    print(f"[multiscene] GPUs={n_gpu} {gpu_names} | SVD cached in {dl_sec}s | installed={installed}", flush=True)

    # Step 3: Parallel Dual-GPU render (1 scene per T4 GPU!)
    self_py = os.path.abspath(__file__)
    procs = []
    for idx, sc in enumerate(scenes):
        gid = idx % max(1, n_gpu)
        l_json = f"/tmp/scene_log_{idx}.json"
        cenv = os.environ.copy()
        cenv["CUDA_VISIBLE_DEVICES"] = str(gid)
        p = subprocess.Popen(
            [
                sys.executable,
                self_py,
                "--worker",
                "--model-dir",
                model_dir,
                "--scene-name",
                sc["name"],
                "--img-path",
                sc["image"],
                "--out-dir",
                str(out_dir),
                "--width",
                str(args.width),
                "--height",
                str(args.height),
                "--steps",
                str(args.steps),
                "--motion",
                str(sc["motion"]),
                "--noise",
                str(sc["noise"]),
                "--seed",
                str(sc["seed"]),
                "--log-json",
                l_json,
            ],
            env=cenv,
        )
        procs.append((idx, sc["name"], p, l_json))
        if n_gpu < 2:
            if p.wait() != 0:
                raise RuntimeError(f"Scene {sc['name']} failed")

    scene_logs = []
    for idx, sname, p, l_json in procs:
        rc = p.wait()
        if rc != 0:
            raise RuntimeError(f"Scene {sname} exited with code {rc}")
        scene_logs.append(json.loads(pathlib.Path(l_json).read_text(encoding="utf-8")))

    shutil.rmtree("/tmp/hf_svd_multi", ignore_errors=True)

    # Step 4: Kaggle AI ($10/day) VLM QA review
    strips = [out_dir / lg["strip"] for lg in scene_logs]
    ai_qa = call_ai_proxy(
        "Inspect these two rendered 5-frame temporal strips of cute cartoon bears at sunset beach. "
        "Rate character face/outline stability and ocean shimmer 0-100. Return ONLY JSON: "
        "{\"scores\": [int, int], \"summary\": \"short assessment\"}",
        strips,
    )
    qa_parsed = extract_json(ai_qa.get("text", "")) if ai_qa.get("ok") else None

    report = {
        "gpu_count": n_gpu,
        "gpu_names": gpu_names,
        "weights_download_sec": dl_sec,
        "ai_director": {"ok": ai_dir.get("ok"), "model": ai_dir.get("model"), "calibrated": parsed_dir},
        "scenes": scene_logs,
        "ai_qa": {"ok": ai_qa.get("ok"), "model": ai_qa.get("model"), "assessment": qa_parsed},
        "total_elapsed_sec": round(time.time() - t0, 2),
    }
    (out_dir / "multiscene_ai_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("MULTISCENE_REPORT=" + json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
