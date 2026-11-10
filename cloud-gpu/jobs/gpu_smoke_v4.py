#!/usr/bin/env python3
"""GPU 冒烟测试载荷（V4）：验证 Kaggle 2xT4 上 torch / CUDA / fair-esm / Drive 上行链路。

只做工程验证，不产生任何科学结论：
  1. 打印 nvidia-smi、torch 版本、可见 GPU 数；
  2. 用 fair-esm 加载 esm2_t12_35M_UR50D，对 8 条公开已知 AMP 序列做前向；
  3. 汇总 embedding 形状 / 有限性 / 耗时；
  4. 若环境中有 DRIVE_UPLOAD_URI，把 JSON 结果 PUT 上去（预授权 resumable 会话）。
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
import traceback
import urllib.request

PEPTIDES = {
    "magainin-2": "GIGKFLHSAKKFGKAFVGEIMNS",
    "melittin": "GIGAVLKVLTTGLPALISWIKRKRQQ",
    "LL-37": "LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES",
    "defensin-HNP1": "ACYCRIPACIAGERRYGTCIYQGRLWAFCC",
    "cecropin-A": "KWKLFKKIEKVGQNIRDGIIKAGPAVAVVGQATQIAK",
    "temporin-1a": "FLPLIGRVLSGIL",
    "protegrin-1": "RGGRLCYCRRRFCVCVGR",
    "indolicidin": "ILPWKWPWWPWRR",
}


def run(cmd: list[str], timeout: int = 60) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (("" if not p.stderr else "\n[stderr] " + p.stderr))
    except Exception as exc:  # noqa: BLE001
        return f"[failed: {exc}]"


def upload(session_uri: str, payload: bytes, mime: str = "application/json") -> dict:
    total = len(payload)
    req = urllib.request.Request(
        session_uri,
        data=payload,
        method="PUT",
        headers={
            "Content-Type": mime,
            "Content-Length": str(total),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Total-Size": str(total),
            "Content-Range": f"bytes 0-{max(total - 1, 0)}/{total}",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return {"status": resp.status, "upload_status": resp.headers.get("X-Goog-Upload-Status"),
                "body": resp.read().decode("utf-8", "replace")[:500]}


def main() -> int:
    out: dict = {
        "script": "gpu_smoke_v4",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "nvidia_smi": run(["nvidia-smi", "-L"])[:2000],
        "nvidia_smi_query": run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,utilization.gpu",
             "--format=csv,noheader"])[:800],
        "steps": {},
    }
    try:
        import torch

        out["torch"] = {
            "version": torch.__version__,
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_version": getattr(torch.version, "cuda", None),
            "device_count": torch.cuda.device_count(),
            "devices": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
        }
    except Exception as exc:  # noqa: BLE001
        out["torch"] = {"error": f"{type(exc).__name__}: {exc}"}
        torch = None

    try:
        t0 = time.time()
        import esm  # fair-esm

        model, alphabet = esm.pretrained.esm2_t12_35M_UR50D()
        model.eval()
        device = "cuda" if (torch is not None and torch.cuda.is_available()) else "cpu"
        model = model.to(device)
        batch_converter = alphabet.get_batch_converter()
        out["steps"]["load_sec"] = round(time.time() - t0, 2)
        out["esm"] = {"version": getattr(esm, "__version__", "unknown"), "model": "esm2_t12_35M_UR50D",
                      "device": device, "alphabet_size": len(alphabet)}

        data = [(k, v) for k, v in PEPTIDES.items()]
        _, _, tokens = batch_converter(data)
        t1 = time.time()
        with torch.no_grad() if torch is not None else _nullcontext():
            tokens = tokens.to(device)
            reps = model(tokens, repr_layers=[12], return_contacts=False)["representations"][12]
        if device == "cuda" and torch is not None:
            torch.cuda.synchronize()
        out["steps"]["forward_sec"] = round(time.time() - t1, 3)

        sizes = [len(s) for s in PEPTIDES.values()]
        lens = [min(s, reps.shape[1] - 2) for s in sizes]
        pooled = []
        for i, l in enumerate(lens):
            vec = reps[i, 1:l + 1].mean(0)
            pooled.append(vec)
        mat = torch.stack(pooled) if torch is not None else None
        out["embedding"] = {
            "dim": int(reps.shape[2]),
            "n_peptides": len(PEPTIDES),
            "max_len": max(sizes),
            "finite": bool(torch.isfinite(mat).all().item()) if torch is not None else None,
            "mean_norm": round(float(mat.norm(dim=1).mean().item()), 4) if torch is not None else None,
            "pairwise_min_cos": round(float((mat / mat.norm(dim=1, keepdim=True)) @ (mat / mat.norm(dim=1, keepdim=True)).T).min().item(), 4) if torch is not None else None,
        }
    except Exception as exc:  # noqa: BLE001
        out["esm"] = {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-1500:]}

    blob = json.dumps(out, ensure_ascii=False, indent=2)
    print(blob, flush=True)

    uri = os.environ.get("DRIVE_UPLOAD_URI")
    if uri:
        try:
            out["upload"] = upload(uri, blob.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            out["upload"] = {"error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps({"upload": out.get("upload")}, ensure_ascii=False), flush=True)

    with open("/kaggle/working/gpu_smoke_v4_result.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return 0


class _nullcontext:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
