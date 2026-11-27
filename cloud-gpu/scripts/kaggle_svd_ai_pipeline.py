#!/usr/bin/env python3
"""Self-contained Dual-GPU Kaggle GPU + Kaggle AI ($10/day Model Proxy) I2V Pipeline.

Combines BOTH Kaggle free quotas in a single automated workflow:
1. Kaggle AI Quota ($10/day, $100/month via `kaggle benchmarks auth` Model Proxy):
   - Pre-render VLM Director: inspects the 5-frame source strip with Gemini / VLM
     to calibrate candidate `(motion_bucket_id, noise_aug_strength, seed)` tuples.
   - Post-render VLM Judge: compares 5-frame strips of all rendered candidates
     against the source strip and selects the highest-fidelity clip automatically.
2. Kaggle Dual-GPU Quota (`NvidiaTeslaT4` = 2x Tesla T4 16 GB VRAM):
   - Pre-downloads `stabilityai/stable-video-diffusion-img2vid-xt` (`fp16` variant only,
     ~4.6 GB) ONCE into `/tmp/hf_svd_model`, then fans out across BOTH T4 GPUs in parallel
     (`CUDA_VISIBLE_DEVICES=0` and `CUDA_VISIBLE_DEVICES=1`) in pure FP16 direct CUDA,
     rendering 4 candidates at 25 denoising steps in ~3 minutes of wall-clock quota.

Privacy guarantee:
- Contains ZERO credentials, tokens, or personal media in source code.
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
import urllib.error
import urllib.request
from typing import Any

DEFAULT_CANDIDATES = [
    {"motion_bucket_id": 115, "noise_aug_strength": 0.02, "seed": 20261126, "rationale": "0yf baseline optical-flow match"},
    {"motion_bucket_id": 100, "noise_aug_strength": 0.015, "seed": 20261127, "rationale": "crisp fur/suit stability"},
    {"motion_bucket_id": 126, "noise_aug_strength": 0.022, "seed": 20261128, "rationale": "brisk handheld forward tracking"},
    {"motion_bucket_id": 88, "noise_aug_strength": 0.012, "seed": 20261129, "rationale": "low-distortion conservative anchor"},
]


def ensure_deps() -> list[str]:
    for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "DIFFUSERS_OFFLINE"):
        os.environ[k] = "0"
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    needed = {
        "imageio": "imageio>=2.34",
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


def encode_lossless_ish_mp4(frames: list[Any], mp4_path: pathlib.Path, fps: int = 10) -> None:
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
        arr = np.asarray(fr.convert("RGB"), dtype=np.uint8)
        proc.stdin.write(arr.tobytes())
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="replace")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed on {mp4_path}: {err[-400:]}")


def _encode_image_b64(path: pathlib.Path, max_w: int = 1280) -> str:
    from PIL import Image

    im = Image.open(path).convert("RGB")
    if im.width > max_w:
        h = int(round(im.height * (max_w / im.width)))
        im = im.resize((max_w, h), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def call_kaggle_ai_proxy(
    prompt: str,
    image_paths: list[pathlib.Path],
    *,
    proxy_url: str | None = None,
    proxy_key: str | None = None,
    preferred_models: list[str] | None = None,
) -> dict[str, Any]:
    """Call Kaggle's $10/day Model Proxy OpenAI-compatible multimodal endpoint."""
    base = (proxy_url or os.environ.get("MODEL_PROXY_URL", "")).strip().rstrip("/")
    key = (proxy_key or os.environ.get("MODEL_PROXY_API_KEY", "")).strip()
    if not base or not key:
        return {"ok": False, "reason": "MODEL_PROXY_URL / MODEL_PROXY_API_KEY not set"}

    for suffix in ("/openapi", "/genai"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    endpoint = f"{base}/openapi/chat/completions"

    env_models = [m.strip() for m in os.environ.get("LLMS_AVAILABLE", "").split(",") if m.strip()]
    discovered: list[str] = []
    if not env_models and not preferred_models:
        try:
            mreq = urllib.request.Request(
                f"{base}/openapi/models",
                headers={"Authorization": f"Bearer {key}"},
                method="GET",
            )
            with urllib.request.urlopen(mreq, timeout=20) as mresp:
                mbody = json.loads(mresp.read().decode("utf-8"))
            raw_ids = [str(it.get("id", "")) for it in (mbody.get("data") or []) if it.get("id")]
            discovered = [
                mid for mid in raw_ids if any(k in mid.lower() for k in ("gemini-3-flash", "gemini-2.5-flash", "gemini", "claude", "gpt-4o"))
            ]
        except Exception:
            pass

    models = (
        preferred_models
        or [m for m in env_models if any(k in m.lower() for k in ("gemini", "claude", "gpt"))]
        or discovered
        or [
            "google/gemini-3-flash-preview",
            "google/gemini-2.5-flash",
            "google/gemini-2.5-pro",
            "anthropic/claude-sonnet-5@default",
        ]
    )

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for p in image_paths:
        b64 = _encode_image_b64(p)
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )

    errors: list[str] = []
    for model in models[:4]:
        payload = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 4096,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            txt = body["choices"][0]["message"]["content"]
            return {"ok": True, "model": model, "text": txt}
        except Exception as exc:
            errors.append(f"{model}: {exc}")
    return {"ok": False, "reason": " | ".join(errors)[:500]}


def extract_json_obj(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def ai_plan_candidates(
    source_strip: pathlib.Path | None, max_candidates: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not source_strip or not source_strip.exists():
        return DEFAULT_CANDIDATES[:max_candidates], {"used_ai": False, "reason": "no source_strip"}

    prompt = (
        f"You are calibrating Stable Video Diffusion XT (25 frames, 576x1024) to replicate "
        f"this real 2.43s handheld rear-follow clip of a small curly white dog in a yellow-green "
        f"four-legged outfit walking forward on a sunlit path (optical-flow baseline motion_bucket_id=115). "
        f"Return ONLY valid JSON with key 'candidates': a list of {max_candidates} dicts spanning crisp "
        f"anatomical stability to realistic forward camera tracking, each having "
        f"'motion_bucket_id' (int 82..135), 'noise_aug_strength' (float 0.01..0.035), "
        f"and 'rationale' (short string)."
    )
    res = call_kaggle_ai_proxy(prompt, [source_strip])
    if not res.get("ok"):
        return DEFAULT_CANDIDATES[:max_candidates], {"used_ai": False, "proxy": res}

    parsed = extract_json_obj(res.get("text", ""))
    cands = (parsed or {}).get("candidates")
    if isinstance(cands, list) and len(cands) >= 1:
        cleaned = []
        for idx, c in enumerate(cands[:max_candidates]):
            mb = max(78, min(140, int(c.get("motion_bucket_id", 115))))
            ns = max(0.008, min(0.04, float(c.get("noise_aug_strength", 0.02))))
            cleaned.append(
                {
                    "motion_bucket_id": mb,
                    "noise_aug_strength": round(ns, 4),
                    "seed": 20261126 + idx,
                    "rationale": str(c.get("rationale", ""))[:200],
                }
            )
        while len(cleaned) < max_candidates:
            fb = dict(DEFAULT_CANDIDATES[len(cleaned) % len(DEFAULT_CANDIDATES)])
            fb["seed"] = 20261126 + len(cleaned)
            cleaned.append(fb)
        return cleaned, {"used_ai": True, "model": res["model"], "candidates": cleaned}
    return DEFAULT_CANDIDATES[:max_candidates], {"used_ai": False, "raw_text": res.get("text", "")[:500]}


def make_strip_from_frames(frames: list[Any], out_path: pathlib.Path, label: str) -> pathlib.Path:
    from PIL import Image, ImageDraw

    idxs = [0, 6, 12, 18, min(24, len(frames) - 1)]
    thumbs = [frames[i].convert("RGB").resize((216, 384), Image.LANCZOS) for i in idxs]
    pad, head = 6, 28
    canvas = Image.new("RGB", (pad + 5 * (216 + pad), head + 384 + pad), (20, 20, 20))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 6), label, fill=(255, 220, 100))
    for i, im in enumerate(thumbs):
        canvas.paste(im, (pad + i * (216 + pad), head))
    canvas.save(out_path, format="JPEG", quality=92)
    return out_path


def ai_judge_winner(
    source_strip: pathlib.Path | None,
    candidate_strips: list[pathlib.Path],
) -> dict[str, Any]:
    imgs = ([source_strip] if source_strip and source_strip.exists() else []) + candidate_strips
    prompt = (
        "Image 1 is the ground-truth 5-frame temporal strip (t=0.0 / 0.6 / 1.2 / 1.8 / 2.36s), followed by "
        f"{len(candidate_strips)} SVD-XT candidate strips (indexed 0..{len(candidate_strips)-1}). "
        "Score each candidate 0-100 on: (1) white dog & yellow-green four-legged outfit anatomical stability, "
        "(2) natural forward walking gait + handheld rear-follow camera progression, "
        "(3) crisp fur/concrete detail and absence of warping/flicker. "
        "Return ONLY JSON: {\"winner_index\": int, \"scores\": [int, ...], \"reason\": \"...\"}"
    )
    res = call_kaggle_ai_proxy(prompt, imgs)
    if not res.get("ok"):
        return {"used_ai": False, "winner_index": 0, "proxy": res}
    parsed = extract_json_obj(res.get("text", "")) or {}
    w = int(parsed.get("winner_index", 0))
    if w < 0 or w >= len(candidate_strips):
        w = 0
    return {
        "used_ai": True,
        "model": res["model"],
        "winner_index": w,
        "scores": parsed.get("scores", []),
        "reason": str(parsed.get("reason", ""))[:500],
    }


def upload_resumable_drive(uri: str, file_path: pathlib.Path, mime: str = "video/mp4") -> dict[str, Any]:
    total = file_path.stat().st_size
    chunk_size = 4 * 1024 * 1024
    offset = 0
    with open(file_path, "rb") as f:
        while offset < total:
            data = f.read(chunk_size)
            end_pos = offset + len(data)
            cmd = "upload, finalize" if end_pos >= total else "upload"
            req = urllib.request.Request(
                uri,
                data=data,
                headers={
                    "Content-Length": str(len(data)),
                    "Content-Type": mime,
                    "X-Goog-Upload-Offset": str(offset),
                    "X-Goog-Upload-Command": cmd,
                    "X-Goog-Upload-Total-Size": str(total),
                },
                method="PUT",
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    status = resp.headers.get("X-Goog-Upload-Status", "")
                    body = resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                if e.code == 308:
                    status = e.headers.get("X-Goog-Upload-Status", "active")
                    body = ""
                else:
                    raise
            offset = end_pos
            if status == "final":
                return {"ok": True, "bytes": total, "status": status, "response": body[:300]}
    return {"ok": True, "bytes": total, "status": "completed"}


def run_worker_shard(
    model_dir: str,
    first_frame: pathlib.Path,
    out_dir: pathlib.Path,
    steps: int,
    tasks_json: str,
    out_log_json: str,
) -> int:
    import numpy as np
    import torch
    from diffusers import StableVideoDiffusionPipeline
    from PIL import Image

    tasks = json.loads(pathlib.Path(tasks_json).read_text(encoding="utf-8"))
    vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    pipe = StableVideoDiffusionPipeline.from_pretrained(
        model_dir,
        torch_dtype=torch.float16,
        variant="fp16",
        local_files_only=True,
    )
    if vram_gb >= 14.0:
        pipe.to("cuda")
        offload_mode = "direct_cuda_fp16"
    else:
        pipe.enable_model_cpu_offload()
        offload_mode = "model_cpu_offload"

    cond_img = Image.open(first_frame).convert("RGB").resize((576, 1024), Image.LANCZOS)
    logs: list[dict[str, Any]] = []

    for item in tasks:
        idx = int(item["index"])
        cfg = item["config"]
        ct0 = time.time()
        gen = torch.Generator(device="cuda" if offload_mode == "direct_cuda_fp16" else "cpu").manual_seed(
            int(cfg["seed"])
        )
        with torch.inference_mode():
            frames = pipe(
                cond_img,
                width=576,
                height=1024,
                num_frames=25,
                num_inference_steps=steps,
                min_guidance_scale=1.0,
                max_guidance_scale=2.5,
                fps=10,
                motion_bucket_id=int(cfg["motion_bucket_id"]),
                noise_aug_strength=float(cfg["noise_aug_strength"]),
                decode_chunk_size=4,
                generator=gen,
            ).frames[0]

        mp4_path = out_dir / f"candidate_{idx}.mp4"
        encode_lossless_ish_mp4(frames, mp4_path, fps=10)

        st_path = out_dir / f"candidate_{idx}_strip.jpg"
        make_strip_from_frames(frames, st_path, f"cand_{idx} motion={cfg['motion_bucket_id']} noise={cfg['noise_aug_strength']} seed={cfg['seed']}")

        arrs = [np.asarray(fr.convert("RGB"), dtype=np.float32) for fr in frames]
        diffs = [float(np.mean(np.abs(arrs[k] - arrs[k - 1]))) for k in range(1, len(arrs))]
        logs.append(
            {
                "index": idx,
                "gpu_visible": os.environ.get("CUDA_VISIBLE_DEVICES", "0"),
                "offload_mode": offload_mode,
                "config": cfg,
                "elapsed_sec": round(time.time() - ct0, 2),
                "mean_motion_mad": round(float(np.mean(diffs)), 3),
                "mp4": mp4_path.name,
                "strip": st_path.name,
                "bytes": mp4_path.stat().st_size,
            }
        )
        print(
            f"[SVD shard GPU={os.environ.get('CUDA_VISIBLE_DEVICES','0')}] candidate_{idx} done in {logs[-1]['elapsed_sec']}s (mad={logs[-1]['mean_motion_mad']})",
            flush=True,
        )

    pathlib.Path(out_log_json).write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--first-frame", required=True, help="Conditioning first frame PNG/JPG")
    ap.add_argument("--source-strip", default="", help="Optional 5-frame ground-truth strip JPG")
    ap.add_argument("--out-dir", default="/kaggle/working", help="Output directory")
    ap.add_argument("--steps", type=int, default=25, help="SVD inference steps")
    ap.add_argument("--max-candidates", type=int, default=4, help="Number of candidates to render & judge")
    ap.add_argument("--worker-shard", action="store_true", help="Internal multi-GPU worker flag")
    ap.add_argument("--model-dir", default="")
    ap.add_argument("--tasks-json", default="")
    ap.add_argument("--out-log-json", default="")
    args = ap.parse_args()

    if args.worker_shard:
        return run_worker_shard(
            args.model_dir,
            pathlib.Path(args.first_frame),
            pathlib.Path(args.out_dir),
            args.steps,
            args.tasks_json,
            args.out_log_json,
        )

    t0 = time.time()
    installed = ensure_deps()
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    first_frame_path = pathlib.Path(args.first_frame)
    if not first_frame_path.is_file():
        raise FileNotFoundError(f"First frame not found: {first_frame_path}")
    source_strip_path = pathlib.Path(args.source_strip) if args.source_strip else None

    import torch
    from huggingface_hub import snapshot_download

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU not available!")

    n_gpu = torch.cuda.device_count()
    gpu_names = [torch.cuda.get_device_name(i) for i in range(n_gpu)]
    vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    print(f"[kaggle_svd_ai] GPUs={n_gpu} {gpu_names} ({vram_gb:.1f} GB each) | installed={installed}", flush=True)

    # Step 1: Kaggle AI ($10/day Model Proxy) Pre-render Director
    candidates, plan_meta = ai_plan_candidates(source_strip_path, max(1, args.max_candidates))
    print(f"[kaggle_svd_ai] AI Director used_ai={plan_meta.get('used_ai')} model={plan_meta.get('model')}", flush=True)

    # Step 2: Download fp16 SVD-XT snapshot ONCE (~4.6 GB) to /tmp/hf_svd_model
    dl_t0 = time.time()
    model_dir = snapshot_download(
        repo_id="stabilityai/stable-video-diffusion-img2vid-xt",
        local_dir="/tmp/hf_svd_model",
        allow_patterns=["*.json", "*.txt", "*fp16*.safetensors"],
    )
    dl_sec = round(time.time() - dl_t0, 2)
    print(f"[kaggle_svd_ai] Cached SVD-XT fp16 weights in {dl_sec}s -> {model_dir}", flush=True)

    # Step 3: Fan out across available GPUs (Dual-T4 parallel execution)
    indexed_tasks = [{"index": i, "config": cfg} for i, cfg in enumerate(candidates)]
    worker_count = min(n_gpu, len(indexed_tasks), 2)
    procs: list[tuple[int, subprocess.Popen[bytes], str]] = []
    self_py = os.path.abspath(__file__)

    for gid in range(worker_count):
        shard = indexed_tasks[gid::worker_count]
        t_json = f"/tmp/svd_tasks_gpu{gid}.json"
        l_json = f"/tmp/svd_logs_gpu{gid}.json"
        pathlib.Path(t_json).write_text(json.dumps(shard), encoding="utf-8")
        cenv = os.environ.copy()
        cenv["CUDA_VISIBLE_DEVICES"] = str(gid)
        p = subprocess.Popen(
            [
                sys.executable,
                self_py,
                "--worker-shard",
                "--model-dir",
                model_dir,
                "--first-frame",
                str(first_frame_path),
                "--out-dir",
                str(out_dir),
                "--steps",
                str(args.steps),
                "--tasks-json",
                t_json,
                "--out-log-json",
                l_json,
            ],
            env=cenv,
        )
        procs.append((gid, p, l_json))

    candidate_logs: list[dict[str, Any]] = []
    for gid, p, l_json in procs:
        rc = p.wait()
        if rc != 0:
            raise RuntimeError(f"GPU worker {gid} exited with code {rc}")
        candidate_logs.extend(json.loads(pathlib.Path(l_json).read_text(encoding="utf-8")))

    shutil.rmtree("/tmp/hf_svd_model", ignore_errors=True)
    candidate_logs.sort(key=lambda x: int(x["index"]))

    rendered_paths = [out_dir / f"candidate_{c['index']}.mp4" for c in candidate_logs]
    strip_paths = [out_dir / f"candidate_{c['index']}_strip.jpg" for c in candidate_logs]

    # Step 4: Kaggle AI ($10/day Model Proxy) Post-render Multimodal VLM Judge
    if len(rendered_paths) > 1:
        judge_meta = ai_judge_winner(source_strip_path, strip_paths)
    else:
        judge_meta = {"used_ai": False, "winner_index": 0, "reason": "single candidate"}
    print(f"[kaggle_svd_ai] AI Judge used_ai={judge_meta.get('used_ai')} winner={judge_meta.get('winner_index')} scores={judge_meta.get('scores')}", flush=True)

    win_idx = int(judge_meta.get("winner_index", 0))
    final_raw = out_dir / "dog_walk_raw.mp4"
    shutil.copy2(rendered_paths[win_idx], final_raw)

    upload_uri = (
        os.environ.get("DRIVE_RAW_UPLOAD_URI", "").strip()
        or os.environ.get("DRIVE_UPLOAD_URI", "").strip()
    )
    drive_meta = None
    if upload_uri:
        drive_meta = upload_resumable_drive(upload_uri, final_raw, "video/mp4")

    report = {
        "gpu_count": n_gpu,
        "gpu_names": gpu_names,
        "vram_gb_per_gpu": round(vram_gb, 2),
        "parallel_workers": worker_count,
        "weights_download_sec": dl_sec,
        "steps": args.steps,
        "ai_director": plan_meta,
        "candidates": candidate_logs,
        "ai_judge": judge_meta,
        "selected_winner_index": win_idx,
        "selected_raw": final_raw.name,
        "selected_bytes": final_raw.stat().st_size,
        "drive_upload": drive_meta,
        "total_elapsed_sec": round(time.time() - t0, 2),
    }
    (out_dir / "ai_judge_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("PIPELINE_REPORT_JSON=" + json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
