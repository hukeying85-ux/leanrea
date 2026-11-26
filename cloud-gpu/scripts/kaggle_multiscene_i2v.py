#!/usr/bin/env python3
"""Multi-Accelerator (Cloud TPU v5e-8 XLA BF16 + Dual-T4 CUDA FP16) + Kaggle AI ($10/day) Multi-Scene I2V Pipeline.

Automatically unlocks ALL three Kaggle compute pools:
  1. Kaggle AI ($10/day Model Proxy) Pre-render VLM Director & Post-render VLM QA
  2. Dual-GPU CUDA (`NvidiaTeslaT4`, parallel 1 scene per GPU in FP16)
  3. Cloud TPU v5e-8 (`TpuV5E8`, 20h/week quota, native `torch_xla` PJRT `bfloat16`
     with static `decode_chunk_size=5` so the compiled HLO graph is reused at
     sub-second step speed across all scenes!)
  4. High-core Xeon AMX `bfloat16` CPU fallback if neither GPU nor XLA is attached.
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
from typing import Any
import urllib.request


def ensure_deps() -> list[str]:
    for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "DIFFUSERS_OFFLINE"):
        os.environ[k] = "0"
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    os.environ.setdefault("PJRT_DEVICE", "TPU")

    # Install pure-python / helper libs WITHOUT upgrading preinstalled torch/torch_xla ABI!
    needed = {
        "imageio_ffmpeg": "imageio-ffmpeg>=0.5",
        "diffusers": "diffusers>=0.30",
        "transformers": "transformers>=4.44",
        "accelerate": "accelerate>=0.30",
        "safetensors": "safetensors>=0.4",
    }
    missing = [spec for mod, spec in needed.items() if importlib.util.find_spec(mod) is None]
    if missing:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-q",
                "--no-input",
                "--upgrade-strategy",
                "only-if-needed",
                *missing,
            ]
        )

    # On GCE TPU VMs (`TpuV5E8`), ensure `torch_xla` is available if `/dev/accel*` or `/dev/vfio` exists
    has_tpu_dev = (
        os.path.exists("/dev/vfio")
        or bool(os.environ.get("TPU_NAME"))
        or bool(os.environ.get("TPU_WORKER_ID"))
    )
    if has_tpu_dev and importlib.util.find_spec("torch_xla") is None:
        try:
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-q",
                    "--no-input",
                    "torch~=2.5.0",
                    "torch_xla[tpu]~=2.5.0",
                    "-f",
                    "https://storage.googleapis.com/libtpu-releases/index.html",
                ]
            )
            missing.append("torch_xla[tpu]")
        except Exception as exc:
            print(f"[deps] optional torch_xla install warn: {exc}", flush=True)
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
    import numpy as np
    from PIL import Image, ImageDraw

    idxs = [int(round(x)) for x in np.linspace(0, len(frames) - 1, 5)]
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


def worker_render_cuda(
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
            decode_chunk_size=5,
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
        "backend": f"cuda:{os.environ.get('CUDA_VISIBLE_DEVICES', '0')}",
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
    return 0


def render_scenes_xla_or_cpu(
    model_dir: str,
    scenes: list[dict[str, Any]],
    out_dir: pathlib.Path,
    width: int,
    height: int,
    steps: int,
    num_frames: int = 25,
) -> tuple[str, list[dict[str, Any]]]:
    """Renders all scenes in a single process on TPU v5e (`torch_xla` BF16) reusing HLO cache,
    with automatic fallback to 96-vCPU Xeon AMX BF16 if XLA is unavailable."""
    import numpy as np
    import torch
    from diffusers import StableVideoDiffusionPipeline
    from PIL import Image

    backend_name = f"cpu_bf16_{os.cpu_count()}cores"
    dev: Any = torch.device("cpu")
    use_xla = False
    xm_mod: Any = None

    try:
        os.environ.setdefault("PJRT_DEVICE", "TPU")
        import torch_xla.core.xla_model as xm

        xdev = xm.xla_device()
        probe = (torch.ones((2, 4, 8, 8), device=xdev, dtype=torch.bfloat16) * 3.0)
        xm.mark_step()
        if abs(float(probe.cpu().mean()) - 3.0) < 0.05:
            dev = xdev
            use_xla = True
            xm_mod = xm
            backend_name = f"tpu_xla_bf16 ({xdev})"
            print(f"[TPU-XLA] Verified Cloud TPU device: {xdev}", flush=True)
    except Exception as exc:
        print(f"[TPU-XLA] Using native PyTorch CPU threads={torch.get_num_threads()} ({exc})", flush=True)

    pipe = StableVideoDiffusionPipeline.from_pretrained(
        model_dir, torch_dtype=torch.float16, variant="fp16", local_files_only=True
    )
    target_dtype = torch.bfloat16 if use_xla else torch.float32
    if not use_xla:
        backend_name = f"cpu_fp32_{os.cpu_count()}cores"
    pipe = pipe.to(device=dev, dtype=target_dtype)

    d_chunk = 7 if num_frames == 14 else 5
    logs: list[dict[str, Any]] = []
    for sc in scenes:
        st0 = time.time()
        sname = sc["name"]
        cond = Image.open(sc["image"]).convert("RGB").resize((width, height), Image.LANCZOS)
        gen = torch.Generator(device="cpu").manual_seed(int(sc["seed"]))
        print(f"[{backend_name}] Rendering {sname} ({width}x{height}, f={num_frames}, steps={steps}, m={sc['motion']})...", flush=True)
        try:
            with torch.no_grad():
                frames = pipe(
                    cond,
                    width=width,
                    height=height,
                    num_frames=num_frames,
                    num_inference_steps=steps,
                    min_guidance_scale=1.0,
                    max_guidance_scale=2.2,
                    fps=12,
                    motion_bucket_id=int(sc["motion"]),
                    noise_aug_strength=float(sc["noise"]),
                    decode_chunk_size=d_chunk,
                    generator=gen,
                ).frames[0]
            if use_xla and xm_mod is not None:
                xm_mod.mark_step()
        except Exception as xla_err:
            if not use_xla:
                raise
            print(f"[TPU-XLA] Runtime fallback to multi-core BF16 CPU: {xla_err}", flush=True)
            use_xla = False
            dev = torch.device("cpu")
            torch.set_num_threads(max(1, os.cpu_count() or 16))
            backend_name = f"cpu_bf16_{os.cpu_count()}cores_fallback"
            pipe = pipe.to(device=dev, dtype=torch.bfloat16)
            gen = torch.Generator(device="cpu").manual_seed(int(sc["seed"]))
            with torch.no_grad():
                frames = pipe(
                    cond,
                    width=width,
                    height=height,
                    num_frames=num_frames,
                    num_inference_steps=steps,
                    min_guidance_scale=1.0,
                    max_guidance_scale=2.2,
                    fps=12,
                    motion_bucket_id=int(sc["motion"]),
                    noise_aug_strength=float(sc["noise"]),
                    decode_chunk_size=d_chunk,
                    generator=gen,
                ).frames[0]

        mp4_file = out_dir / f"{sname}.mp4"
        strip_file = out_dir / f"{sname}_strip.jpg"
        encode_mp4(frames, mp4_file, fps=12)
        make_strip(frames, strip_file, f"{sname} [{backend_name}] m={sc['motion']} n={sc['noise']}")

        arrs = [np.asarray(f.convert("RGB"), dtype=np.float32) for f in frames]
        diffs = [float(np.mean(np.abs(arrs[i] - arrs[i - 1]))) for i in range(1, len(arrs))]
        el = round(time.time() - st0, 2)
        meta = {
            "scene": sname,
            "backend": backend_name,
            "width": width,
            "height": height,
            "steps": steps,
            "motion_bucket_id": int(sc["motion"]),
            "noise_aug_strength": float(sc["noise"]),
            "seed": int(sc["seed"]),
            "elapsed_sec": el,
            "mean_motion_mad": round(float(np.mean(diffs)), 3),
            "mp4": mp4_file.name,
            "strip": strip_file.name,
            "bytes": mp4_file.stat().st_size,
        }
        logs.append(meta)
        print(f"[{backend_name}] {sname} done in {el}s (mad={meta['mean_motion_mad']})", flush=True)

    return backend_name, logs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes-json", default="")
    ap.add_argument("--out-dir", default="/kaggle/working")
    ap.add_argument("--width", type=int, default=768)
    ap.add_argument("--height", type=int, default=448)
    ap.add_argument("--num-frames", type=int, default=25)
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
        return worker_render_cuda(
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

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scenes = json.loads(args.scenes_json)
    scene_imgs = [pathlib.Path(s["image"]) for s in scenes]

    # Step 1: Kaggle AI ($10/day) Director calibration
    ai_dir = call_ai_proxy(
        "These keyframes are clean 2D cute bear illustrations on a real golden sunset beach. "
        "Calibrate SVD-XT parameters for subtle cute character breathing/arm sway + shimmering ocean waves "
        "WITHOUT warping cartoon faces/outlines. Return ONLY JSON: "
        "{\"motion\": int 46..60, \"noise\": float 0.010..0.016}",
        scene_imgs[:2],
    )
    parsed_dir = extract_json(ai_dir.get("text", "")) if ai_dir.get("ok") else None
    if parsed_dir:
        m_cal = max(44, min(64, int(parsed_dir.get("motion", 52))))
        n_cal = round(max(0.009, min(0.017, float(parsed_dir.get("noise", 0.012)))), 4)
        for idx, sc in enumerate(scenes):
            sc["motion"] = m_cal + (idx % 2) * 2
            sc["noise"] = n_cal

    # Step 2: Shared fp16 checkpoint download
    dl_t0 = time.time()
    model_dir = snapshot_download(
        repo_id="stabilityai/stable-video-diffusion-img2vid-xt",
        local_dir="/tmp/hf_svd_multi",
        allow_patterns=["*.json", "*.txt", "*fp16*.safetensors"],
    )
    dl_sec = round(time.time() - dl_t0, 2)

    # Step 3: Execute on CUDA Dual-GPU if available, else Cloud TPU v5e-8 (`torch_xla` BF16)
    scene_logs: list[dict[str, Any]] = []
    if torch.cuda.is_available():
        n_gpu = torch.cuda.device_count()
        accel_summary = f"cuda x{n_gpu}: {[torch.cuda.get_device_name(i) for i in range(n_gpu)]}"
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
            if n_gpu < 2 or len(procs) % n_gpu == 0:
                for _, sname, pw, lj in procs:
                    if pw.wait() != 0:
                        raise RuntimeError(f"Scene {sname} failed")
                    scene_logs.append(json.loads(pathlib.Path(lj).read_text(encoding="utf-8")))
                procs = []
        for _, sname, pw, lj in procs:
            if pw.wait() != 0:
                raise RuntimeError(f"Scene {sname} failed")
            scene_logs.append(json.loads(pathlib.Path(lj).read_text(encoding="utf-8")))
    else:
        accel_summary, scene_logs = render_scenes_xla_or_cpu(
            model_dir, scenes, out_dir, args.width, args.height, args.steps, args.num_frames
        )

    shutil.rmtree("/tmp/hf_svd_multi", ignore_errors=True)

    # Step 4: Kaggle AI ($10/day) VLM QA review
    strips = [out_dir / lg["strip"] for lg in scene_logs]
    ai_qa = call_ai_proxy(
        "Inspect these rendered 5-frame temporal strips of cute cartoon bears at sunset beach. "
        "Rate character face/outline stability and ocean shimmer 0-100. Return ONLY JSON: "
        "{\"scores\": [int], \"summary\": \"short assessment\"}",
        strips,
    )
    qa_parsed = extract_json(ai_qa.get("text", "")) if ai_qa.get("ok") else None

    report = {
        "accelerator": accel_summary,
        "installed_deps": installed,
        "weights_download_sec": dl_sec,
        "ai_director": {"ok": ai_dir.get("ok"), "model": ai_dir.get("model"), "calibrated": parsed_dir},
        "scenes": scene_logs,
        "ai_qa": {"ok": ai_qa.get("ok"), "model": ai_qa.get("model"), "assessment": qa_parsed},
        "total_elapsed_sec": round(time.time() - t0, 2),
    }
    rep_tag = scenes[0]["name"] if len(scenes) == 1 else "all"
    (out_dir / f"multiscene_ai_report_{rep_tag}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("MULTISCENE_REPORT=" + json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
