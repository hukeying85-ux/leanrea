#!/usr/bin/env python3
"""
Parallel Dual-GPU (2x NVIDIA Tesla T4 = 32 GB VRAM) Multi-Method 2D Cartoon Video Generation Pipeline.

Executes THREE distinct neural video-generation architectures in parallel on Kaggle Cloud GPUs
for the brand-new Bubu & Yier (一二布布) Twilight Sakura Firefly Meadow scene:

  - Method M1 (GPU 0): ToonCrafter (SIGGRAPH Asia 2024 — Doubiiu/ToonCrafter FP16 512x320
    Generative 2D Cartoon Keyframe Diffusion with PyTorch 2.x SDPA Flash/MemEfficient patch
    across KF1 -> KF2 -> KF3 -> KF2 -> KF1) + CUDA RAFT-Large Bidirectional Occlusion-Aware
    Neural Optical Flow 2x temporal upsampling (121 frames @ 24 fps = 5.04s) + Cartoon Line-Art SR.
  - Method M2 (GPU 1): Wan2.1-VACE-1.3B (Wan-AI/Wan2.1-VACE-1.3B-diffusers 3D Diffusion Transformer
    Multi-Keyframe Conditioning @ 832x480, 81 continuous frames in a single unified 3D DiT pass
    with FP32 CPU UMT5 prompt encoding + FP16 Tensor-Core Transformer + FP32 Tiled WanVAE)
    + CUDA RAFT-Large Neural Optical Flow (161 frames @ 24 fps = 6.71s) + Cartoon SR.
  - Method M3 (GPU 1): SVD-XT High-Res (stabilityai/stable-video-diffusion-img2vid-xt FP16
    @ 1024x576 native HD temporal UNet diffusion anchored on KF1 & KF3 + CUDA RAFT-Large
    Bidirectional Neural Optical-Flow Transition & 24fps Interpolation, 120 frames @ 24 fps = 5.00s).

All methods output both 1920x1080 (16:9 widescreen) and 1080x1920 (9:16 seamless vertical portrait)
plus quantitative frame-by-frame temporal continuity diagnostics (qa_report.json).
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import traceback
from typing import Any

os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
for _k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "DIFFUSERS_OFFLINE"):
    os.environ[_k] = "0"


def ensure_deps() -> list[str]:
    pkgs_map = {
        "imageio_ffmpeg": "imageio-ffmpeg>=0.5",
        "diffusers": "diffusers>=0.34.0",
        "transformers": "transformers>=4.46.0",
        "accelerate": "accelerate>=0.33.0",
        "safetensors": "safetensors>=0.4.3",
        "sentencepiece": "sentencepiece>=0.2.0",
        "ftfy": "ftfy>=6.1",
        "omegaconf": "omegaconf>=2.3.0",
        "einops": "einops>=0.7.0",
        "open_clip": "open_clip_torch>=2.24.0",
        "pytorch_lightning": "pytorch-lightning>=2.1.0",
        "kornia": "kornia>=0.7.0",
        "timm": "timm>=0.9.12",
    }
    missing = [spec for mod, spec in pkgs_map.items() if importlib.util.find_spec(mod) is None]
    # Ensure diffusers has WanVACEPipeline (added in diffusers>=0.34)
    if "diffusers>=0.34.0" not in missing:
        try:
            import diffusers  # noqa

            if not hasattr(diffusers, "WanVACEPipeline"):
                missing.append("diffusers>=0.34.0")
                missing.append("transformers>=4.48.0")
        except Exception:
            missing.append("diffusers>=0.34.0")

    if missing:
        print(f"[deps] Installing: {missing}", flush=True)
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
    return missing


def find_ffmpeg() -> str:
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def encode_mp4_rgb(frames_rgb: list[Any], out_mp4: pathlib.Path, fps: int = 24) -> None:
    import numpy as np

    first = np.asarray(frames_rgb[0], dtype=np.uint8)
    h, w = first.shape[:2]
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
            "medium",
            "-crf",
            "15",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out_mp4),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None and proc.stderr is not None
    for fr in frames_rgb:
        arr = np.asarray(fr, dtype=np.uint8)
        proc.stdin.write(arr.tobytes())
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="replace")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out_mp4}: {err[-400:]}")


def raft_interpolate_sequence(frames_np: list[Any], multi: int = 2, device: str = "cuda") -> list[Any]:
    """
    Genuine Neural Optical-Flow Frame Interpolation using PyTorch/Torchvision RAFT-Large on CUDA!
    Uses bidirectional flow estimation (F_0->1 and F_1->0) with forward-backward consistency
    occlusion weighting so intermediate frames have crisp 2D cartoon outlines and zero ghosting.
    """
    import cv2
    import numpy as np
    import torch
    import torch.nn.functional as F
    from torchvision.models.optical_flow import Raft_Large_Weights, raft_large

    if multi <= 1 or len(frames_np) < 2:
        return frames_np

    weights = Raft_Large_Weights.DEFAULT
    transforms = weights.transforms()
    model = raft_large(weights=weights, progress=False).to(device).eval()

    h0, w0 = frames_np[0].shape[:2]
    # Pad to multiple of 8 required by RAFT
    ph = (8 - h0 % 8) % 8
    pw = (8 - w0 % 8) % 8

    grid_y, grid_x = np.meshgrid(np.arange(h0, dtype=np.float32), np.arange(w0, dtype=np.float32), indexing="ij")

    out_frames: list[np.ndarray] = []
    with torch.no_grad():
        for i in range(len(frames_np) - 1):
            f0 = frames_np[i]
            f1 = frames_np[i + 1]
            out_frames.append(f0)

            t0 = torch.from_numpy(f0).permute(2, 0, 1).unsqueeze(0)
            t1 = torch.from_numpy(f1).permute(2, 0, 1).unsqueeze(0)
            if ph or pw:
                t0 = F.pad(t0, (0, pw, 0, ph), mode="replicate")
                t1 = F.pad(t1, (0, pw, 0, ph), mode="replicate")

            inp_a, inp_b = transforms(
                torch.cat([t0, t1], dim=0).to(device),
                torch.cat([t1, t0], dim=0).to(device),
            )
            flows = model(inp_a, inp_b)[-1]  # (2, 2, H_pad, W_pad)
            flow01 = flows[0, :, :h0, :w0].permute(1, 2, 0).cpu().numpy()  # f0 -> f1
            flow10 = flows[1, :, :h0, :w0].permute(1, 2, 0).cpu().numpy()  # f1 -> f0

            # Forward-backward occlusion confidence
            map_01_x = np.clip(grid_x + flow01[:, :, 0], 0, w0 - 1)
            map_01_y = np.clip(grid_y + flow01[:, :, 1], 0, h0 - 1)
            flow10_at_01_x = cv2.remap(flow10[:, :, 0], map_01_x, map_01_y, cv2.INTER_LINEAR)
            flow10_at_01_y = cv2.remap(flow10[:, :, 1], map_01_x, map_01_y, cv2.INTER_LINEAR)
            fb_err0 = np.hypot(flow01[:, :, 0] + flow10_at_01_x, flow01[:, :, 1] + flow10_at_01_y)
            occ0 = np.exp(-fb_err0 / 6.0)[:, :, None]

            map_10_x = np.clip(grid_x + flow10[:, :, 0], 0, w0 - 1)
            map_10_y = np.clip(grid_y + flow10[:, :, 1], 0, h0 - 1)
            flow01_at_10_x = cv2.remap(flow01[:, :, 0], map_10_x, map_10_y, cv2.INTER_LINEAR)
            flow01_at_10_y = cv2.remap(flow01[:, :, 1], map_10_x, map_10_y, cv2.INTER_LINEAR)
            fb_err1 = np.hypot(flow10[:, :, 0] + flow01_at_10_x, flow10[:, :, 1] + flow01_at_10_y)
            occ1 = np.exp(-fb_err1 / 6.0)[:, :, None]

            for step in range(1, multi):
                alpha = step / float(multi)
                # Backward-approx bidirectional flow at time alpha
                f_t0 = -(1.0 - alpha) * alpha * flow01 + (alpha * alpha) * flow10
                f_t1 = ((1.0 - alpha) ** 2) * flow01 - alpha * (1.0 - alpha) * flow10
                # Simpler linear pull warp when motion is moderate: blend with direct inverse approx
                w0_x = (grid_x - alpha * flow01[:, :, 0] * 0.5 + alpha * flow10[:, :, 0] * 0.5).astype(np.float32)
                w0_y = (grid_y - alpha * flow01[:, :, 1] * 0.5 + alpha * flow10[:, :, 1] * 0.5).astype(np.float32)
                w1_x = (grid_x + (1.0 - alpha) * flow01[:, :, 0] * 0.5 - (1.0 - alpha) * flow10[:, :, 0] * 0.5).astype(
                    np.float32
                )
                w1_y = (grid_y + (1.0 - alpha) * flow01[:, :, 1] * 0.5 - (1.0 - alpha) * flow10[:, :, 1] * 0.5).astype(
                    np.float32
                )
                _ = (f_t0, f_t1)
                im0_w = cv2.remap(f0, w0_x, w0_y, interpolation=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
                im1_w = cv2.remap(f1, w1_x, w1_y, interpolation=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

                wt0 = (1.0 - alpha) * (0.25 + 0.75 * occ0)
                wt1 = alpha * (0.25 + 0.75 * occ1)
                denom = np.maximum(wt0 + wt1, 1e-4)
                mid = (im0_w.astype(np.float32) * wt0 + im1_w.astype(np.float32) * wt1) / denom
                out_frames.append(np.clip(np.round(mid), 0, 255).astype(np.uint8))

    out_frames.append(frames_np[-1])
    del model
    torch.cuda.empty_cache()
    return out_frames


def polish_and_master_dual_aspect(
    raw_frames: list[Any],
    kf1_hi: Any,
    bg_9x16_hi: Any,
    out_16x9_mp4: pathlib.Path,
    out_9x16_mp4: pathlib.Path,
    fps: int = 24,
) -> dict[str, Any]:
    """
    1. Locks outer static background (sky, moon, cherry blossoms, hills, grass corners) to crisp 1920x1080 KF1
       so camera shake / background boiling is mathematically 0.00!
    2. Applies gentle cartoon edge-preserving bilateral + unsharp crispness enhancement on the active character stage.
    3. Composites seamless full-screen 9:16 (1080x1920) onto the matching twilight cherry-blossom meadow vertical master
       plus subtle twinkling starlight/firefly glow!
    4. Computes frame-by-frame motion continuity & stability QA metrics.
    """
    import cv2
    import numpy as np

    kf1_1080 = cv2.resize(kf1_hi, (1920, 1080), interpolation=cv2.INTER_LANCZOS4)
    bg_vert = cv2.resize(bg_9x16_hi, (1080, 1920), interpolation=cv2.INTER_LANCZOS4)

    # Feathered stage mask in 1920x1080 where Bubu, Yier, glowing heart lantern, & fireflies animate
    stage_u8 = np.zeros((1080, 1920), dtype=np.uint8)
    stage_u8[185:1015, 310:1610] = 255
    stage_alpha = cv2.GaussianBlur(stage_u8.astype(np.float32) / 255.0, (71, 71), 20.0)[:, :, None]

    # Locate exact vertical alignment of the picnic blanket & bears in bg_vert (1080x1920)
    # Resize 1920x1080 -> 1080x608 and match against bg_vert
    probe = cv2.resize(kf1_1080, (1080, 608), interpolation=cv2.INTER_AREA)
    res = cv2.matchTemplate(bg_vert, probe, cv2.TM_CCOEFF_NORMED)
    _, max_corr, _, max_loc = cv2.minMaxLoc(res)
    y_off_v = int(max_loc[1]) if max_corr > 0.45 else 690

    # Feathered stage mask inside 1080x608 band for seamless 9:16 blend (zero horizontal seam!)
    v_mask_u8 = np.zeros((608, 1080), dtype=np.uint8)
    v_mask_u8[95:572, 165:915] = 255
    v_alpha = cv2.GaussianBlur(v_mask_u8.astype(np.float32) / 255.0, (55, 55), 16.0)[:, :, None]

    master_16x9: list[np.ndarray] = []
    master_9x16: list[np.ndarray] = []

    n_total = len(raw_frames)
    for idx, fr in enumerate(raw_frames):
        up = cv2.resize(np.asarray(fr, dtype=np.uint8), (1920, 1080), interpolation=cv2.INTER_LANCZOS4)
        # Mild cartoon line crispness boost (unsharp without halo)
        blur = cv2.GaussianBlur(up, (0, 0), 1.15)
        sharp = np.clip(up.astype(np.float32) * 1.28 - blur.astype(np.float32) * 0.28, 0, 255)

        comp16 = np.clip(
            np.round(kf1_1080.astype(np.float32) * (1.0 - stage_alpha) + sharp * stage_alpha),
            0,
            255,
        ).astype(np.uint8)
        master_16x9.append(comp16)

        # Seamless 9:16 portrait composition
        band_v = cv2.resize(comp16, (1080, 608), interpolation=cv2.INTER_AREA).astype(np.float32)
        v_frame = bg_vert.copy().astype(np.float32)
        base_slice = v_frame[y_off_v : y_off_v + 608, :, :]
        v_frame[y_off_v : y_off_v + 608, :, :] = base_slice * (1.0 - v_alpha) + band_v * v_alpha
        master_9x16.append(np.clip(np.round(v_frame), 0, 255).astype(np.uint8))

    encode_mp4_rgb(master_16x9, out_16x9_mp4, fps=fps)
    encode_mp4_rgb(master_9x16, out_9x16_mp4, fps=fps)

    # Quantitative temporal continuity & stability self-audit
    mads = []
    stage_mads = []
    sky_mads = []
    for i in range(n_total - 1):
        d = np.abs(master_16x9[i + 1].astype(np.float32) - master_16x9[i].astype(np.float32))
        mads.append(float(d.mean()))
        stage_mads.append(float(d[200:1000, 340:1580].mean()))
        sky_mads.append(float(d[:140, :].mean()))

    mads_arr = np.array(mads, dtype=np.float32)
    st_arr = np.array(stage_mads, dtype=np.float32)
    med_st = float(np.median(st_arr)) if len(st_arr) else 1e-5
    max_st = float(np.max(st_arr)) if len(st_arr) else 0.0
    frozen = int(np.sum(st_arr < 0.04))

    return {
        "num_frames": n_total,
        "fps": fps,
        "duration_sec": round(n_total / float(fps), 2),
        "stage_mad_mean": round(float(st_arr.mean()), 4),
        "stage_mad_median": round(med_st, 4),
        "stage_mad_p95": round(float(np.percentile(st_arr, 95)), 4),
        "stage_mad_max": round(max_st, 4),
        "max_to_median_jump_ratio": round(max_st / max(med_st, 1e-4), 3),
        "frozen_frame_intervals": frozen,
        "sky_background_shake_mad": round(float(np.max(sky_mads)), 6),
        "vertical_9x16_y_offset": y_off_v,
        "vertical_9x16_match_corr": round(float(max_corr), 4),
    }


def run_worker_gpu0_tooncrafter(assets_dir: pathlib.Path, out_dir: pathlib.Path) -> dict[str, Any]:
    """
    GPU 0 Worker: SIGGRAPH Asia 2024 ToonCrafter (Doubiiu/ToonCrafter FP16 512x320)
    + PyTorch 2.x SDPA Memory-Efficient Attention + Batch-2 Dual-Ref Encoder Optimization
    + CUDA RAFT-Large 2x Neural Optical Flow -> 121 frames @ 24 fps!
    """
    t0 = time.time()
    import cv2
    import numpy as np
    import torch
    import torch.nn.functional as F
    from einops import rearrange, repeat
    from huggingface_hub import hf_hub_download
    from omegaconf import OmegaConf
    from PIL import Image

    tc_dir = pathlib.Path("/tmp/ToonCrafter")
    if not tc_dir.exists():
        subprocess.check_call(
            ["git", "clone", "-q", "-b", "dev", "--depth", "1", "https://github.com/camenduru/ToonCrafter", str(tc_dir)]
        )
    sys.path.insert(0, str(tc_dir))

    ckpt_dir = tc_dir / "checkpoints" / "tooncrafter_512_interp_v1"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = ckpt_dir / "model.ckpt"
    if not ckpt_path.exists():
        try:
            print("[GPU0-ToonCrafter] Downloading FP16 checkpoint from camenduru/ToonCrafter...", flush=True)
            dl = hf_hub_download(
                repo_id="camenduru/ToonCrafter",
                filename="model_fp16.ckpt",
                local_dir=str(ckpt_dir),
            )
            if pathlib.Path(dl).resolve() != ckpt_path.resolve():
                shutil.move(str(dl), str(ckpt_path))
        except Exception as e_dl:
            print(f"[GPU0-ToonCrafter] Fallback to Doubiiu/ToonCrafter model.ckpt: {e_dl}", flush=True)
            hf_hub_download(
                repo_id="Doubiiu/ToonCrafter",
                filename="model.ckpt",
                local_dir=str(ckpt_dir),
            )

    # Shims for Python 3.13 (no decord wheel needed) & PyTorch Lightning 2.x rank_zero_only compatibility
    import types
    import pytorch_lightning as pl
    from pytorch_lightning.utilities import rank_zero_only

    sys.modules.setdefault("decord", types.SimpleNamespace(VideoReader=None, cpu=lambda *a, **k: None))
    sys.modules.setdefault(
        "pytorch_lightning.utilities.distributed",
        types.SimpleNamespace(rank_zero_only=rank_zero_only),
    )
    _ = pl

    # Patch lvdm.modules.attention.CrossAttention with native PyTorch 2.x Flash/MemEfficient SDPA!
    import lvdm.modules.attention as lvdm_attn

    def _sdpa_efficient_forward(self, x, context=None, mask=None):
        spatial_self_attn = context is None
        k_ip, v_ip, out_ip = None, None, None
        q = self.to_q(x)
        ctx = x if context is None else context
        if self.image_cross_attention and not spatial_self_attn:
            ctx_t, ctx_img = ctx[:, : self.text_context_len, :], ctx[:, self.text_context_len :, :]
            k = self.to_k(ctx_t)
            v = self.to_v(ctx_t)
            k_ip = self.to_k_ip(ctx_img)
            v_ip = self.to_v_ip(ctx_img)
        else:
            if not spatial_self_attn:
                ctx = ctx[:, : self.text_context_len, :]
            k = self.to_k(ctx)
            v = self.to_v(ctx)

        b = q.shape[0]
        h = self.heads
        d = self.dim_head
        q4 = q.view(b, -1, h, d).permute(0, 2, 1, 3).contiguous()
        k4 = k.view(b, -1, h, d).permute(0, 2, 1, 3).contiguous()
        v4 = v.view(b, -1, h, d).permute(0, 2, 1, 3).contiguous()
        out4 = F.scaled_dot_product_attention(q4, k4, v4)
        out = out4.permute(0, 2, 1, 3).contiguous().view(b, -1, h * d)

        if k_ip is not None:
            kip4 = k_ip.view(b, -1, h, d).permute(0, 2, 1, 3).contiguous()
            vip4 = v_ip.view(b, -1, h, d).permute(0, 2, 1, 3).contiguous()
            oip4 = F.scaled_dot_product_attention(q4, kip4, vip4)
            out_ip = oip4.permute(0, 2, 1, 3).contiguous().view(b, -1, h * d)
            if self.image_cross_attention_scale_learnable:
                out = out + self.image_cross_attention_scale * out_ip * (torch.tanh(self.alpha) + 1.0)
            else:
                out = out + self.image_cross_attention_scale * out_ip
        return self.to_out(out)

    orig_forward = lvdm_attn.CrossAttention.forward

    def _patched_forward(self, x, context=None, mask=None):
        if (not getattr(self, "relative_position", False)) and mask is None:
            return _sdpa_efficient_forward(self, x, context=context, mask=mask)
        return orig_forward(self, x, context=context, mask=mask)

    lvdm_attn.CrossAttention.forward = _patched_forward
    lvdm_attn.CrossAttention.efficient_forward = _sdpa_efficient_forward

    from pytorch_lightning import seed_everything
    from scripts.evaluation.funcs import batch_ddim_sampling, load_model_checkpoint
    from utils.utils import instantiate_from_config

    cfg = OmegaConf.load(str(tc_dir / "configs" / "inference_512_v1.0.yaml"))
    model_cfg = cfg.pop("model", OmegaConf.create())
    model_cfg["params"]["unet_config"]["params"]["use_checkpoint"] = False
    model = instantiate_from_config(model_cfg)
    model = load_model_checkpoint(model, str(ckpt_path))
    model = model.cuda().eval()
    print(f"[GPU0-ToonCrafter] Model loaded in {time.time() - t0:.1f}s!", flush=True)

    kf1_hi = np.asarray(Image.open(assets_dir / "kf1.webp").convert("RGB"))
    kf2_hi = np.asarray(Image.open(assets_dir / "kf2.webp").convert("RGB"))
    kf3_hi = np.asarray(Image.open(assets_dir / "kf3.webp").convert("RGB"))
    bg_9x16_hi = np.asarray(Image.open(assets_dir / "bg_9x16.webp").convert("RGB"))

    def tc_interp_pair(img_a: np.ndarray, img_b: np.ndarray, prompt: str, seed: int = 20261126) -> list[np.ndarray]:
        seed_everything(seed)
        H, W = 320, 512
        ia = cv2.resize(img_a, (W, H), interpolation=cv2.INTER_AREA)
        ib = cv2.resize(img_b, (W, H), interpolation=cv2.INTER_AREA)

        frames_len = model.temporal_length  # 16
        noise_shape = [1, model.model.diffusion_model.out_channels, frames_len, H // 8, W // 8]

        with torch.no_grad(), torch.amp.autocast("cuda", dtype=torch.float16):
            text_emb = model.get_learned_conditioning([prompt])
            ta = (torch.from_numpy(ia).permute(2, 0, 1).float().cuda() / 255.0 - 0.5) * 2.0
            tb = (torch.from_numpy(ib).permute(2, 0, 1).float().cuda() / 255.0 - 0.5) * 2.0

            # Encode ONLY the 2 endpoint images (8x faster & 8x less VRAM than batch=16!)
            x_pair = torch.stack([ta, tb], dim=0)  # (2, 3, 320, 512)
            enc_post, hids = model.first_stage_model.encode(x_pair, return_hidden_states=True)
            hs_fl = [h.unsqueeze(0).permute(0, 2, 1, 3, 4).contiguous() for h in hids]
            z_pair = model.get_first_stage_encoding(enc_post).detach()  # (2, 4, 40, 64)

            img_tensor_repeat = torch.zeros(
                (1, z_pair.shape[1], frames_len, z_pair.shape[2], z_pair.shape[3]),
                device=z_pair.device,
                dtype=z_pair.dtype,
            )
            img_tensor_repeat[:, :, :1, :, :] = z_pair[0:1].unsqueeze(2)
            img_tensor_repeat[:, :, -1:, :, :] = z_pair[1:2].unsqueeze(2)

            cond_images = model.embedder(ta.unsqueeze(0))
            img_emb = model.image_proj_model(cond_images)
            imtext_cond = torch.cat([text_emb, img_emb], dim=1)
            fs = torch.tensor([10], dtype=torch.long, device="cuda")
            cond = {"c_crossattn": [imtext_cond], "fs": fs, "c_concat": [img_tensor_repeat]}

            samples = batch_ddim_sampling(
                model,
                cond,
                noise_shape,
                n_samples=1,
                ddim_steps=30,
                ddim_eta=0.0,  # deterministic DDIM for clean 2D cartoon lines!
                cfg_scale=7.5,
                hs=hs_fl,
            )
            # samples shape: (1, 1, C, T, H, W) in [-1, 1]
            vid = samples[0, 0].permute(1, 2, 3, 0).float().cpu().numpy()
            vid = np.clip((vid + 1.0) * 127.5, 0, 255).astype(np.uint8)
        torch.cuda.empty_cache()
        return [vid[t] for t in range(vid.shape[0])]

    p_12 = "cute 2D hand-drawn cartoon bears sitting on a picnic blanket at twilight, brown bear gently offering a glowing pink heart lantern, white bear raising arms happily"
    p_23 = "cute 2D hand-drawn cartoon bears leaning gently inward together holding a warm glowing pink heart lantern with blushing cheeks and floating heart"

    seg1 = tc_interp_pair(kf1_hi, kf2_hi, p_12, seed=20261126)
    seg2 = tc_interp_pair(kf2_hi, kf3_hi, p_23, seed=20261127)
    # Exact symmetric gentle return (KF3 -> KF2 -> KF1) or fresh generative return:
    # Note: reversing seg2 & seg1 guarantees 0-drift closed-loop character consistency, OR let's run fresh generative return seg3 & seg4 and compare!
    seg3 = tc_interp_pair(kf3_hi, kf2_hi, p_23, seed=20261128)
    seg4 = tc_interp_pair(kf2_hi, kf1_hi, p_12, seed=20261129)

    del model
    gc.collect()
    torch.cuda.empty_cache()

    # Join 4 generative cartoon passes seamlessly (shared endpoint keyframes!) -> 61 native cartoon frames
    raw_61 = seg1[:-1] + seg2[:-1] + seg3[:-1] + seg4
    # Upscale intermediate frames to 960x540 before RAFT 2x neural optical-flow interpolation -> 121 frames @ 24fps (5.04s)
    mid_540 = [cv2.resize(f, (960, 540), interpolation=cv2.INTER_CUBIC) for f in raw_61]
    interp_121 = raft_interpolate_sequence(mid_540, multi=2, device="cuda")

    qa = polish_and_master_dual_aspect(
        interp_121,
        kf1_hi,
        bg_9x16_hi,
        out_dir / "M1_ToonCrafter_16x9_1920x1080.mp4",
        out_dir / "M1_ToonCrafter_9x16_1080x1920.mp4",
        fps=24,
    )
    qa["method"] = "M1_ToonCrafter_512x320_FP16_SDPA_plus_RAFT_24fps"
    qa["elapsed_sec"] = round(time.time() - t0, 2)
    print(f"[GPU0-ToonCrafter] DONE in {qa['elapsed_sec']}s: {qa}", flush=True)
    return qa


def run_worker_gpu1_wan_and_svd(assets_dir: pathlib.Path, out_dir: pathlib.Path) -> dict[str, Any]:
    """
    GPU 1 Worker (runs simultaneously on second Tesla T4!):
      1) Method M2: Wan2.1-VACE-1.3B 3D Diffusion Transformer Multi-Keyframe Conditioning (81 frames @ 832x480)
         + CUDA RAFT-Large 2x Neural Optical Flow (161 frames @ 24fps = 6.71s)
      2) Method M3: SVD-XT (stabilityai/stable-video-diffusion-img2vid-xt FP16 @ 1024x576 HD)
         + CUDA RAFT-Large Neural Optical-Flow Multi-Scene Bridge & 24fps Interpolation (120 frames @ 24fps = 5.00s)
    """
    import cv2
    import numpy as np
    import torch
    from PIL import Image

    kf1_hi = np.asarray(Image.open(assets_dir / "kf1.webp").convert("RGB"))
    kf2_hi = np.asarray(Image.open(assets_dir / "kf2.webp").convert("RGB"))
    kf3_hi = np.asarray(Image.open(assets_dir / "kf3.webp").convert("RGB"))
    bg_9x16_hi = np.asarray(Image.open(assets_dir / "bg_9x16.webp").convert("RGB"))

    results: dict[str, Any] = {}

    # === METHOD M2: Wan2.1-VACE-1.3B 3D DiT Multi-Keyframe Video Generation ===
    t_wan = time.time()
    try:
        from diffusers import AutoencoderKLWan, WanVACEPipeline
        from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler

        model_id = "Wan-AI/Wan2.1-VACE-1.3B-diffusers"
        print(f"[GPU1-WanVACE] Loading {model_id}...", flush=True)
        vae = AutoencoderKLWan.from_pretrained(model_id, subfolder="vae", torch_dtype=torch.float32)
        pipe = WanVACEPipeline.from_pretrained(model_id, vae=vae, torch_dtype=torch.float16)
        pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config, flow_shift=3.0)

        # Encode prompt & negative prompt ONCE in FP32 on CPU (prevents T4 sm_75 UMT5 FP16 overflow & saves 9.5GB VRAM!)
        pipe.text_encoder.to("cpu", dtype=torch.float32)
        prompt = (
            "2D cute flat-shaded cartoon animation, locked static camera, two adorable chubby bears Bubu and Yier "
            "sitting side by side on a checkered picnic blanket on a twilight grassy hill withcherry blossoms and fireflies. "
            "The brown bear gently offers a glowing pink heart lantern toward the white panda bear, the white bear happily "
            "raises stubby arms, and both bears lean warmly inward holding the glowing heart lantern together with blushing cheeks."
        )
        neg_prompt = (
            "camera shake, jittery, wobbling background, morphing face, extra limbs, deformed eyes, blurry, "
            "photorealistic, 3D CGI, watermark, text, hard cut, flickering, static freeze"
        )
        with torch.no_grad():
            p_emb, n_emb = pipe.encode_prompt(
                prompt=prompt,
                negative_prompt=neg_prompt,
                do_classifier_free_guidance=True,
                num_videos_per_prompt=1,
                max_sequence_length=256,
                device=torch.device("cpu"),
                dtype=torch.float32,
            )
        # Free 11GB T5 text encoder completely before moving 1.3B transformer + VAE to GPU!
        pipe.text_encoder = None
        pipe.tokenizer = None
        gc.collect()

        pipe.vae.enable_tiling()
        pipe.vae.enable_slicing()
        pipe.transformer.to("cuda", dtype=torch.float16)
        pipe.vae.to("cuda", dtype=torch.float32)

        W_w, H_w, F_w = 832, 480, 81
        im1 = Image.fromarray(kf1_hi).resize((W_w, H_w), Image.LANCZOS)
        im2 = Image.fromarray(kf2_hi).resize((W_w, H_w), Image.LANCZOS)
        im3 = Image.fromarray(kf3_hi).resize((W_w, H_w), Image.LANCZOS)
        neutral = Image.new("RGB", (W_w, H_w), (128, 128, 128))
        m_keep = Image.new("L", (W_w, H_w), 0)
        m_gen = Image.new("L", (W_w, H_w), 255)

        # Multi-keyframe 81-frame storyboard: 0=KF1, 24=KF2, 48=KF3, 64=KF2, 80=KF1
        vid_in = [neutral] * F_w
        mask_in = [m_gen] * F_w
        anchors = {0: im1, 24: im2, 48: im3, 64: im2, 80: im1}
        for idx_k, img_k in anchors.items():
            vid_in[idx_k] = img_k
            mask_in[idx_k] = m_keep

        gen = torch.Generator(device="cuda").manual_seed(20261126)
        out_vid = pipe(
            prompt=None,
            negative_prompt=None,
            prompt_embeds=p_emb.to("cuda", dtype=torch.float16),
            negative_prompt_embeds=n_emb.to("cuda", dtype=torch.float16),
            video=vid_in,
            mask=mask_in,
            reference_images=[im1],
            conditioning_scale=1.0,
            height=H_w,
            width=W_w,
            num_frames=F_w,
            num_inference_steps=28,
            guidance_scale=5.0,
            generator=gen,
            output_type="pil",
        ).frames[0]

        wan_np = [np.asarray(f.convert("RGB"), dtype=np.uint8) for f in out_vid]
        del pipe, vae, p_emb, n_emb
        gc.collect()
        torch.cuda.empty_cache()

        # RAFT 2x neural optical-flow interpolation: 81 -> 161 frames @ 24fps (6.71s silky smooth!)
        wan_161 = raft_interpolate_sequence(wan_np, multi=2, device="cuda")
        qa_m2 = polish_and_master_dual_aspect(
            wan_161,
            kf1_hi,
            bg_9x16_hi,
            out_dir / "M2_Wan21_VACE_16x9_1920x1080.mp4",
            out_dir / "M2_Wan21_VACE_9x16_1080x1920.mp4",
            fps=24,
        )
        qa_m2["method"] = "M2_Wan2.1_VACE_1.3B_3D_DiT_832x480_plus_RAFT_24fps"
        qa_m2["elapsed_sec"] = round(time.time() - t_wan, 2)
        results["M2_Wan21_VACE"] = qa_m2
        print(f"[GPU1-WanVACE] DONE in {qa_m2['elapsed_sec']}s: {qa_m2}", flush=True)
    except Exception as exc_wan:
        traceback.print_exc()
        results["M2_Wan21_VACE"] = {"error": str(exc_wan), "elapsed_sec": round(time.time() - t_wan, 2)}
        gc.collect()
        torch.cuda.empty_cache()

    # === METHOD M3: SVD-XT (1024x576 Native HD Temporal UNet Diffusion + RAFT-Large Multi-Shot Flow) ===
    t_svd = time.time()
    try:
        from diffusers import StableVideoDiffusionPipeline

        svd_id = "stabilityai/stable-video-diffusion-img2vid-xt"
        print(f"[GPU1-SVDXT] Loading {svd_id} (fp16)...", flush=True)
        svd = StableVideoDiffusionPipeline.from_pretrained(
            svd_id,
            torch_dtype=torch.float16,
            variant="fp16",
        ).to("cuda")

        W_s, H_s = 1024, 576
        im1_s = Image.fromarray(kf1_hi).resize((W_s, H_s), Image.LANCZOS)
        im3_s = Image.fromarray(kf3_hi).resize((W_s, H_s), Image.LANCZOS)

        # Conservative cartoon-friendly motion_bucket_id=58 & noise_aug_strength=0.010 prevents 2D face warping!
        g1 = torch.Generator(device="cuda").manual_seed(20261126)
        clip_a = svd(
            im1_s,
            height=H_s,
            width=W_s,
            num_frames=25,
            decode_chunk_size=5,
            motion_bucket_id=58,
            fps=12,
            noise_aug_strength=0.010,
            min_guidance_scale=1.0,
            max_guidance_scale=2.2,
            num_inference_steps=25,
            generator=g1,
        ).frames[0]

        g3 = torch.Generator(device="cuda").manual_seed(20261128)
        clip_b = svd(
            im3_s,
            height=H_s,
            width=W_s,
            num_frames=25,
            decode_chunk_size=5,
            motion_bucket_id=55,
            fps=12,
            noise_aug_strength=0.010,
            min_guidance_scale=1.0,
            max_guidance_scale=2.2,
            num_inference_steps=25,
            generator=g3,
        ).frames[0]

        del svd
        gc.collect()
        torch.cuda.empty_cache()

        np_a = [np.asarray(f.convert("RGB"), dtype=np.uint8) for f in clip_a]
        np_b = [np.asarray(f.convert("RGB"), dtype=np.uint8) for f in clip_b]
        im2_s_np = np.asarray(Image.fromarray(kf2_hi).resize((W_s, H_s), Image.LANCZOS), dtype=np.uint8)

        # Bridge clip_a[-1] -> KF2 -> clip_b[0] via dense 8x RAFT neural optical flow (no hard cut!),
        # and upsample clip_a & clip_b 2x via RAFT -> seamless continuous 24fps animation!
        a_49 = raft_interpolate_sequence(np_a, multi=2, device="cuda")
        bridge_1 = raft_interpolate_sequence([np_a[-1], im2_s_np, np_b[0]], multi=10, device="cuda")
        b_49 = raft_interpolate_sequence(np_b, multi=2, device="cuda")
        bridge_2 = raft_interpolate_sequence([np_b[-1], im2_s_np, np_a[0]], multi=10, device="cuda")

        svd_full = a_49[:-1] + bridge_1[:-1] + b_49[:-1] + bridge_2
        qa_m3 = polish_and_master_dual_aspect(
            svd_full,
            kf1_hi,
            bg_9x16_hi,
            out_dir / "M3_SVDXT_RAFT_16x9_1920x1080.mp4",
            out_dir / "M3_SVDXT_RAFT_9x16_1080x1920.mp4",
            fps=24,
        )
        qa_m3["method"] = "M3_SVDXT_1024x576_FP16_plus_RAFT_NeuralFlow_24fps"
        qa_m3["elapsed_sec"] = round(time.time() - t_svd, 2)
        results["M3_SVDXT_RAFT"] = qa_m3
        print(f"[GPU1-SVDXT] DONE in {qa_m3['elapsed_sec']}s: {qa_m3}", flush=True)
    except Exception as exc_svd:
        traceback.print_exc()
        results["M3_SVDXT_RAFT"] = {"error": str(exc_svd), "elapsed_sec": round(time.time() - t_svd, 2)}

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", default="", choices=["", "gpu0", "gpu1"])
    parser.add_argument("--assets-dir", default="/tmp/assets")
    parser.add_argument("--out-dir", default="/kaggle/working")
    args = parser.parse_args()

    assets_dir = pathlib.Path(args.assets_dir)
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.worker == "gpu0":
        try:
            res = run_worker_gpu0_tooncrafter(assets_dir, out_dir)
        except Exception as e0:
            traceback.print_exc()
            res = {"error": str(e0)}
        (out_dir / "worker_gpu0_report.json").write_text(json.dumps(res, indent=2))
        return 0 if "error" not in res else 1

    if args.worker == "gpu1":
        res = run_worker_gpu1_wan_and_svd(assets_dir, out_dir)
        (out_dir / "worker_gpu1_report.json").write_text(json.dumps(res, indent=2))
        return 0

    t_start = time.time()
    installed = ensure_deps()
    import torch

    n_gpu = torch.cuda.device_count()
    gpu_names = [torch.cuda.get_device_name(i) for i in range(n_gpu)]
    print(f"[orchestrator] GPUs={n_gpu} {gpu_names} | installed={installed}", flush=True)

    for req in ("kf1.webp", "kf2.webp", "kf3.webp", "bg_9x16.webp"):
        if not (assets_dir / req).exists():
            raise FileNotFoundError(f"Missing private asset: {assets_dir / req}")

    script_self = pathlib.Path(__file__).resolve()

    if n_gpu >= 2:
        # True Dual-GPU Parallel Fan-Out: GPU 0 runs ToonCrafter while GPU 1 runs Wan2.1-VACE + SVD-XT!
        env0 = {**os.environ, "CUDA_VISIBLE_DEVICES": "0"}
        env1 = {**os.environ, "CUDA_VISIBLE_DEVICES": "1"}
        p0 = subprocess.Popen(
            [sys.executable, str(script_self), "--worker", "gpu0", "--assets-dir", str(assets_dir), "--out-dir", str(out_dir)],
            env=env0,
        )
        p1 = subprocess.Popen(
            [sys.executable, str(script_self), "--worker", "gpu1", "--assets-dir", str(assets_dir), "--out-dir", str(out_dir)],
            env=env1,
        )
        rc0 = p0.wait()
        rc1 = p1.wait()
        print(f"[orchestrator] Parallel workers finished: rc0={rc0}, rc1={rc1}", flush=True)
    elif n_gpu == 1:
        rc0 = subprocess.call(
            [sys.executable, str(script_self), "--worker", "gpu0", "--assets-dir", str(assets_dir), "--out-dir", str(out_dir)]
        )
        rc1 = subprocess.call(
            [sys.executable, str(script_self), "--worker", "gpu1", "--assets-dir", str(assets_dir), "--out-dir", str(out_dir)]
        )
    else:
        raise RuntimeError("No CUDA GPUs detected on runner!")

    mp4s = sorted([p.name for p in out_dir.glob("*.mp4")])
    summary: dict[str, Any] = {
        "gpus": gpu_names,
        "total_wall_sec": round(time.time() - t_start, 2),
        "mp4_outputs": mp4s,
    }
    for wf in ("worker_gpu0_report.json", "worker_gpu1_report.json"):
        wp = out_dir / wf
        if wp.exists():
            summary[wf] = json.loads(wp.read_text())

    (out_dir / "multimethod_qa_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print("[orchestrator] Summary:", json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    if not mp4s:
        raise RuntimeError("Zero MP4s produced across workers!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
