#!/usr/bin/env python3
"""Kaggle Cloud GPU + Kaggle AI ($10/day Model Proxy) Controller.

Zero-leak guarantee:
  - Never commits personal media, credentials, or run logs to Git.
  - Transfers private decrypted inputs from PRIVATE_INPUTS_DIR directly into private Kaggle Kernels (`is_private: true`).
  - Injects short-lived `MODEL_PROXY_URL` / `MODEL_PROXY_API_KEY` ($10/day AI quota) into private Kernels.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any

QUEUE_DEFAULT = "cloud-gpu/jobs/queue.json"
RUNS_DIR_DEFAULT = "cloud-gpu/runs"
MAX_INLINE_BYTES = 2 * 1024 * 1024


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_cmd(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 600,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        env=env,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def resolve_kaggle_env() -> tuple[dict[str, str], str | None]:
    env = os.environ.copy()
    if env.get("KAGGLE_API_TOKEN", "").strip():
        return env, "env:KAGGLE_API_TOKEN"
    if env.get("KAGGLE_USERNAME", "").strip() and env.get("KAGGLE_KEY", "").strip():
        return env, "env:KAGGLE_USERNAME+KAGGLE_KEY"

    vault_token = os.path.expanduser("~/.gpu-relay/kaggle_token")
    if os.path.exists(vault_token):
        raw = open(vault_token, "r", encoding="utf-8").read().strip()
        if raw:
            if raw.startswith("{"):
                data = json.loads(raw)
                env["KAGGLE_USERNAME"] = data["username"]
                env["KAGGLE_KEY"] = data["key"]
                return env, "vault:kaggle.json"
            if ":" in raw and not raw.startswith("KGAT_"):
                user, key = raw.split(":", 1)
                env["KAGGLE_USERNAME"] = user.strip()
                env["KAGGLE_KEY"] = key.strip()
                return env, "vault:username:key"
            env["KAGGLE_API_TOKEN"] = raw
            return env, "vault:KAGGLE_API_TOKEN"

    for p in ("~/.kaggle/access_token", "~/.kaggle/kaggle.json", "~/.kaggle/credentials.json"):
        exp = os.path.expanduser(p)
        if os.path.exists(exp):
            return env, exp
    return env, None


def get_kaggle_username(env: dict[str, str]) -> str:
    if env.get("KAGGLE_USERNAME", "").strip():
        return env["KAGGLE_USERNAME"].strip()

    code = (
        "import json\n"
        "from kaggle.api.kaggle_api_extended import KaggleApi\n"
        "api = KaggleApi()\n"
        "api.authenticate()\n"
        "print(json.dumps({'username': api.config_values.get('username', '')}))\n"
    )
    res = run_cmd([sys.executable, "-c", code], env=env, timeout=45)
    if res.returncode != 0:
        raise RuntimeError(f"Kaggle auth failed: {(res.stderr or res.stdout).strip()[:400]}")
    for line in reversed(res.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            uname = json.loads(line).get("username", "").strip()
            if uname:
                return uname
    raise RuntimeError("Authenticated with Kaggle, but could not determine username.")


def _upload_bundle_if_requested(src_dir: str, bundle_uri_env: str = "DRIVE_BUNDLE_UPLOAD_URI") -> dict[str, Any] | None:
    uri = os.environ.get(bundle_uri_env, "").strip()
    if not uri:
        return None
    from drive_put import upload_resumable

    tar_path = tempfile.mktemp(suffix=".tar.gz", prefix="kag_bundle_")
    try:
        with tarfile.open(tar_path, "w:gz") as tf:
            for root, _, files in os.walk(src_dir):
                for fn in sorted(files):
                    full = os.path.join(root, fn)
                    arc = os.path.relpath(full, src_dir)
                    tf.add(full, arcname=arc)
        return upload_resumable(uri, tar_path, "application/gzip")
    finally:
        if os.path.exists(tar_path):
            os.remove(tar_path)


def execute_probe(job: dict[str, Any], run_dir: str) -> dict[str, Any]:
    kaggle_env, kag_src = resolve_kaggle_env()
    report: dict[str, Any] = {
        "job_id": job["id"],
        "provider": "probe",
        "timestamp_utc": utc_now(),
        "python_version": sys.version.split()[0],
        "kaggle_cli": shutil.which("kaggle"),
        "kaggle": {"configured": bool(kag_src), "credential_source": kag_src, "authenticated": False},
    }

    if kag_src and shutil.which("kaggle"):
        try:
            uname = get_kaggle_username(kaggle_env)
            report["kaggle"]["authenticated"] = True
            report["kaggle"]["username"] = uname
            qcode = (
                "import json\n"
                "from kaggle.api.kaggle_api_extended import KaggleApi\n"
                "api = KaggleApi(); api.authenticate()\n"
                "from kagglesdk.kernels.types.kernels_api_service import ApiGetAcceleratorQuotaStatisticsRequest\n"
                "with api.build_kaggle_client() as c:\n"
                "    r = c.kernels.kernels_api_client.get_accelerator_quota_statistics(ApiGetAcceleratorQuotaStatisticsRequest())\n"
                "    print('QUOTA_JSON=' + json.dumps(str(r)))\n"
            )
            qres = run_cmd([sys.executable, "-c", qcode], env=kaggle_env, timeout=45)
            report["kaggle"]["quota_raw"] = (qres.stdout or qres.stderr).strip()[:1200]
        except Exception as exc:
            report["kaggle"]["error"] = str(exc)

    report["status"] = "completed"
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return report


def execute_kaggle_job(job: dict[str, Any], run_dir: str) -> dict[str, Any]:
    kaggle_env, kag_src = resolve_kaggle_env()
    if not kag_src:
        raise RuntimeError("Kaggle credentials not configured.")
    if not shutil.which("kaggle"):
        raise RuntimeError("`kaggle` CLI not installed.")

    mode = job.get("mode", "run")
    username = get_kaggle_username(kaggle_env)
    slug = re.sub(r"[^a-z0-9-]", "-", job.get("kernel_slug") or f"gpu-job-{job['id']}".lower()).strip("-")
    kernel_ref = f"{username}/{slug}"

    if mode == "status":
        st = run_cmd(["kaggle", "kernels", "status", kernel_ref], env=kaggle_env, timeout=45)
        payload = {
            "job_id": job["id"],
            "provider": "kaggle",
            "mode": "status",
            "kernel_ref": kernel_ref,
            "status_output": (st.stdout or st.stderr).strip(),
            "checked_at_utc": utc_now(),
        }
        with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as rf:
            json.dump(payload, rf, ensure_ascii=False, indent=2)
            rf.write("\n")
        return payload

    if mode == "output":
        status_history: list[str] = []
        final_st = "unknown"
        if job.get("wait", False):
            deadline = time.time() + int(job.get("timeout_sec", 600))
            max_q_deadline = time.time() + int(job.get("max_queue_sec", 240))
            while time.time() < deadline:
                st = run_cmd(["kaggle", "kernels", "status", kernel_ref], env=kaggle_env, timeout=45)
                raw_txt = (st.stdout or st.stderr).strip()
                if not status_history or status_history[-1] != raw_txt:
                    status_history.append(raw_txt)
                    print(f"[kaggle output-wait] {utc_now()} -> {raw_txt}", flush=True)
                low = raw_txt.lower()
                if "complete" in low:
                    final_st = "completed"
                    break
                if "error" in low or "cancel" in low:
                    final_st = "failed"
                    break
                if "queued" in low and time.time() > max_q_deadline:
                    final_st = "stuck_queued"
                    break
                time.sleep(20)
        out_sub = os.path.join(run_dir, "outputs")
        os.makedirs(out_sub, exist_ok=True)
        out = run_cmd(["kaggle", "kernels", "output", kernel_ref, "-p", out_sub, "-o"], env=kaggle_env, timeout=300)
        bundle_meta = _upload_bundle_if_requested(out_sub) if os.listdir(out_sub) else None
        copied = _copy_small_outputs(out_sub, run_dir)
        payload = {
            "job_id": job["id"],
            "provider": "kaggle",
            "mode": "output",
            "kernel_ref": kernel_ref,
            "final_status": final_st,
            "status_history": status_history,
            "copied_files": copied,
            "all_output_files": sorted(os.listdir(out_sub)),
            "bundle_upload": bundle_meta,
            "cli_output": (out.stdout or out.stderr).strip()[:800],
            "fetched_at_utc": utc_now(),
        }
        with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as rf:
            json.dump(payload, rf, ensure_ascii=False, indent=2)
            rf.write("\n")
        return payload

    acc = job.get("accelerator", "NvidiaTeslaT4")
    enable_tpu = acc.lower().startswith("tpu")
    enable_gpu = acc.upper() not in ("CPU", "NONE") and not enable_tpu
    script_path = job["script_path"]
    script_args = job.get("script_args", [])
    extra_pip = job.get("extra_pip", [])

    with open(script_path, "r", encoding="utf-8") as sf:
        script_src = sf.read()

    injected_env: dict[str, str] = {"GPU_RELAY_ASSETS_DIR": "/tmp/assets"}
    for k in (
        "DRIVE_UPLOAD_URI",
        "DRIVE_ENDPOINT_UPLOAD_URI",
        "DRIVE_RAW_UPLOAD_URI",
        "MODEL_PROXY_URL",
        "MODEL_PROXY_API_KEY",
        "LLMS_AVAILABLE",
        "LLM_DEFAULT",
        "LLM_DEFAULT_EVAL",
    ):
        if os.environ.get(k):
            injected_env[k] = os.environ[k]

    # Collect private in-memory inputs from PRIVATE_INPUTS_DIR (never stored in Git)
    attached_b85: dict[str, str] = {}
    priv_dir = os.environ.get("PRIVATE_INPUTS_DIR", "").strip()
    if priv_dir and os.path.isdir(priv_dir):
        for root, _, files in os.walk(priv_dir):
            for fn in sorted(files):
                fpath = os.path.join(root, fn)
                with open(fpath, "rb") as af:
                    attached_b85[fn] = base64.b85encode(af.read()).decode("ascii")

    for apath in job.get("attach_files", []):
        if os.path.isfile(apath):
            with open(apath, "rb") as af:
                attached_b85[os.path.basename(apath)] = base64.b85encode(af.read()).decode("ascii")

    stage_dir = tempfile.mkdtemp(prefix="kag_push_")
    try:
        entry_py = os.path.join(stage_dir, "entry_main.py")
        pip_snippet = (
            f"import subprocess, sys\nsubprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *{repr(extra_pip)}])\n"
            if extra_pip
            else ""
        )
        wrapper = (
            "import base64, os, sys, runpy\n"
            f"{pip_snippet}"
            f"os.environ.update({repr(injected_env)})\n"
            "os.makedirs('/tmp/assets', exist_ok=True)\n"
            f"_ASSETS = {repr(attached_b85)}\n"
            "for _fn, _b85 in _ASSETS.items():\n"
            "    _raw = base64.b85decode(_b85)\n"
            "    with open(os.path.join('/tmp', _fn), 'wb') as _af1:\n"
            "        _af1.write(_raw)\n"
            "    with open(os.path.join('/tmp/assets', _fn), 'wb') as _af2:\n"
            "        _af2.write(_raw)\n"
            "del _ASSETS\n"
            f"with open('/tmp/_payload.py', 'w', encoding='utf-8') as _f:\n"
            f"    _f.write({repr(script_src)})\n"
            f"sys.argv = ['/tmp/_payload.py', *{repr([str(a) for a in script_args])}]\n"
            "runpy.run_path('/tmp/_payload.py', run_name='__main__')\n"
        )
        with open(entry_py, "w", encoding="utf-8") as ef:
            ef.write(wrapper)
        entry_kb = round(os.path.getsize(entry_py) / 1024, 1)
        print(f"[kaggle push] Prepared {kernel_ref} entry_main.py ({entry_kb} KiB)", flush=True)

        title = " ".join(slug.split("-"))
        if len(title) < 5:
            title = f"{title} kernel"
        metadata = {
            "id": kernel_ref,
            "title": title,
            "code_file": "entry_main.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": "true",
            "enable_gpu": "true" if enable_gpu else "false",
            "enable_tpu": "true" if enable_tpu else "false",
            "enable_internet": "true",
            "machine_shape": acc if acc.upper() not in ("CPU", "NONE") else "",
            "dataset_sources": job.get("dataset_sources", []),
            "competition_sources": job.get("competition_sources", []),
            "kernel_sources": job.get("kernel_sources", []),
            "model_sources": job.get("model_sources", []),
        }
        with open(os.path.join(stage_dir, "kernel-metadata.json"), "w", encoding="utf-8") as mf:
            json.dump(metadata, mf, indent=2)

        push_py = (
            "import json, os, sys\n"
            "from kaggle.api.kaggle_api_extended import KaggleApi\n"
            "api = KaggleApi(); api.authenticate()\n"
            f"sdir = {repr(stage_dir)}\n"
            f"tout = {repr(str(min(int(job.get('timeout_sec', 1080)), 1200)))}\n"
            f"acc = {repr(acc if acc and acc.upper() not in ('CPU','NONE') else None)}\n"
            "def _try_push():\n"
            "    r = api.kernels_push(sdir, timeout=tout, acc=acc)\n"
            "    if getattr(r, 'error', ''):\n"
            "        raise RuntimeError('SAVE_KERNEL_ERR: ' + str(r.error))\n"
            "    print('PUSH_OK:', getattr(r, 'ref', ''), getattr(r, 'versionNumber', ''))\n"
            "try:\n"
            "    _try_push()\n"
            "except Exception as e1:\n"
            "    resp = getattr(e1, 'response', None)\n"
            "    body = getattr(resp, 'text', '') if resp is not None else ''\n"
            "    print('SCRIPT_PUSH_WARN:', type(e1).__name__, e1, body[:400], flush=True)\n"
            "    src_txt = open(os.path.join(sdir, 'entry_main.py'), 'r', encoding='utf-8').read()\n"
            "    nb = {'cells': [{'cell_type': 'code', 'execution_count': None, 'metadata': {}, 'outputs': [], 'source': [src_txt]}], 'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}, 'language_info': {'name': 'python'}}, 'nbformat': 4, 'nbformat_minor': 5}\n"
            "    open(os.path.join(sdir, 'entry_main.ipynb'), 'w', encoding='utf-8').write(json.dumps(nb))\n"
            "    os.remove(os.path.join(sdir, 'entry_main.py'))\n"
            "    meta = json.load(open(os.path.join(sdir, 'kernel-metadata.json'), 'r', encoding='utf-8'))\n"
            "    meta['code_file'] = 'entry_main.ipynb'; meta['kernel_type'] = 'notebook'\n"
            "    open(os.path.join(sdir, 'kernel-metadata.json'), 'w', encoding='utf-8').write(json.dumps(meta, indent=2))\n"
            "    try:\n"
            "        _try_push()\n"
            "    except Exception as e2:\n"
            "        r2 = getattr(e2, 'response', None)\n"
            "        b2 = getattr(r2, 'text', '') if r2 is not None else ''\n"
            "        sys.exit(f'{type(e2).__name__}: {e2} | BODY={b2[:600]}')\n"
        )
        pushed = run_cmd([sys.executable, "-c", push_py], env=kaggle_env, timeout=120)
        if pushed.returncode != 0:
            raise RuntimeError(f"kaggle kernels push failed ({entry_kb} KiB): {(pushed.stderr or pushed.stdout).strip()}")
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)

    wait_for_completion = bool(job.get("wait", mode == "run"))
    copied_files: list[str] = []
    all_output_files: list[str] = []
    bundle_meta: dict[str, Any] | None = None
    status_history: list[str] = []
    final_status = "pushed_async"

    if wait_for_completion:
        poll_timeout = int(job.get("timeout_sec", 1200))
        deadline = time.time() + poll_timeout
        while time.time() < deadline:
            time.sleep(20)
            st = run_cmd(["kaggle", "kernels", "status", kernel_ref], env=kaggle_env, timeout=45)
            raw_txt = (st.stdout or st.stderr).strip()
            if not status_history or status_history[-1] != raw_txt:
                status_history.append(raw_txt)
                print(f"[kaggle poll] {utc_now()} -> {raw_txt}", flush=True)
            txt = raw_txt.lower()
            if "complete" in txt:
                final_status = "completed"
                break
            if "error" in txt or "cancel" in txt:
                final_status = "failed"
                break
        out_sub = os.path.join(run_dir, "outputs")
        os.makedirs(out_sub, exist_ok=True)
        run_cmd(["kaggle", "kernels", "output", kernel_ref, "-p", out_sub, "-o"], env=kaggle_env, timeout=300)
        all_output_files = sorted(os.listdir(out_sub))
        bundle_meta = _upload_bundle_if_requested(out_sub)
        copied_files = _copy_small_outputs(out_sub, run_dir)

    payload = {
        "job_id": job["id"],
        "provider": "kaggle",
        "mode": mode,
        "accelerator": acc,
        "kernel_ref": kernel_ref,
        "attached_private_files": sorted(attached_b85.keys()),
        "model_proxy_injected": bool(injected_env.get("MODEL_PROXY_API_KEY")),
        "status": final_status,
        "status_history": status_history,
        "all_output_files": all_output_files,
        "copied_files": copied_files,
        "bundle_upload": bundle_meta,
        "push_output": (pushed.stdout or "").strip()[:500],
        "updated_at_utc": utc_now(),
    }
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as rf:
        json.dump(payload, rf, ensure_ascii=False, indent=2)
        rf.write("\n")

    if final_status == "failed":
        raise RuntimeError(f"Kaggle kernel {kernel_ref} ended with error; inspect logs in result report.")
    return payload


def _copy_small_outputs(src_root: str, dst_dir: str) -> list[str]:
    copied: list[str] = []
    for root, _, files in os.walk(src_root):
        for fn in files:
            full = os.path.join(root, fn)
            if os.path.getsize(full) <= MAX_INLINE_BYTES and not fn.endswith(
                (".pt", ".pth", ".safetensors", ".onnx", ".gguf", ".mp4", ".gif", ".png", ".jpg", ".wav")
            ):
                rel = os.path.relpath(full, src_root).replace(os.sep, "_")
                shutil.copy2(full, os.path.join(dst_dir, rel))
                copied.append(rel)
    return sorted(copied)


def cmd_doctor(_: argparse.Namespace) -> int:
    _, kag = resolve_kaggle_env()
    pubkey = os.path.exists("cloud-gpu/relay_pubkey.pem")
    info = {
        "python": sys.version.split()[0],
        "local_kaggle_cli": shutil.which("kaggle"),
        "gh_cli": shutil.which("gh"),
        "local_kaggle_credentials": kag,
        "relay_pubkey_ready": pubkey,
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def cmd_enqueue(args: argparse.Namespace) -> int:
    qpath = args.queue
    os.makedirs(os.path.dirname(os.path.abspath(qpath)), exist_ok=True)
    queue: dict[str, Any] = {"jobs": []}
    if os.path.exists(qpath):
        with open(qpath, "r", encoding="utf-8") as f:
            queue = json.load(f)

    provider = args.provider
    acc = args.accelerator or ("NvidiaTeslaT4" if provider == "kaggle" else "")
    job_id = args.id or f"{provider}-{dt.datetime.now(dt.timezone.utc).strftime('%m%d-%H%M%S')}"
    job: dict[str, Any] = {
        "id": job_id,
        "provider": provider,
        "mode": args.mode,
        "accelerator": acc,
        "script_path": args.script or "",
        "script_args": shlex.split(args.script_args) if args.script_args else [],
        "extra_pip": shlex.split(args.extra_pip) if args.extra_pip else [],
        "wait": not args.async_push,
        "timeout_sec": args.timeout_sec,
        "status": "pending",
        "created_at_utc": utc_now(),
    }
    if args.kernel_slug:
        job["kernel_slug"] = args.kernel_slug
    if args.dataset_sources:
        job["dataset_sources"] = [s.strip() for s in args.dataset_sources.split(",") if s.strip()]
    if args.attach_files:
        job["attach_files"] = [s.strip() for s in args.attach_files.split(",") if s.strip()]

    queue["jobs"] = [j for j in queue.get("jobs", []) if j.get("id") != job_id] + [job]
    with open(qpath, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(job, ensure_ascii=False, indent=2))
    return 0


def cmd_run_queue(args: argparse.Namespace) -> int:
    qpath = args.queue
    if not os.path.exists(qpath):
        print(f"No queue file at {qpath}; nothing to do.")
        return 0
    with open(qpath, "r", encoding="utf-8") as f:
        queue = json.load(f)

    any_failed = False
    for job in queue.get("jobs", []):
        if args.only_id and job.get("id") != args.only_id:
            continue
        if job.get("status") not in ("pending", "retry") and not args.force:
            continue

        job_id = job["id"]
        run_dir = os.path.join(args.runs_dir, job_id)
        os.makedirs(run_dir, exist_ok=True)
        print(f"=== Running job {job_id} ({job.get('provider')} / {job.get('mode')}) ===", flush=True)
        try:
            prov = job["provider"]
            if prov == "probe":
                res = execute_probe(job, run_dir)
            elif prov == "kaggle":
                res = execute_kaggle_job(job, run_dir)
            else:
                raise ValueError(f"Unsupported provider: {prov}")
            job["status"] = res.get("status", "completed")
            job["finished_at_utc"] = utc_now()
        except Exception as exc:
            any_failed = True
            job["status"] = "failed"
            job["error"] = str(exc)
            job["finished_at_utc"] = utc_now()
            err_payload = {"job_id": job_id, "status": "failed", "error": str(exc), "timestamp_utc": utc_now()}
            with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as ef:
                json.dump(err_payload, ef, ensure_ascii=False, indent=2)
                ef.write("\n")
            print(f"[ERROR] Job {job_id} failed: {exc}", file=sys.stderr, flush=True)

    with open(qpath, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return 1 if any_failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Kaggle Cloud GPU + AI Controller.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Check local & relay credential readiness")

    p_enq = sub.add_parser("enqueue", help="Enqueue a GPU job into cloud-gpu/jobs/queue.json")
    p_enq.add_argument("--queue", default=QUEUE_DEFAULT)
    p_enq.add_argument("--id", help="Explicit job ID")
    p_enq.add_argument("--provider", choices=["probe", "kaggle"], default="kaggle")
    p_enq.add_argument("--mode", choices=["probe", "run", "status", "output"], default="run")
    p_enq.add_argument("--accelerator", default="")
    p_enq.add_argument("--script", default="")
    p_enq.add_argument("--script-args", default="")
    p_enq.add_argument("--extra-pip", default="")
    p_enq.add_argument("--async-push", action="store_true")
    p_enq.add_argument("--kernel-slug", default="")
    p_enq.add_argument("--dataset-sources", default="")
    p_enq.add_argument("--attach-files", default="")
    p_enq.add_argument("--timeout-sec", type=int, default=1200)

    p_run = sub.add_parser("run-queue", help="Execute pending jobs in queue.json")
    p_run.add_argument("--queue", default=QUEUE_DEFAULT)
    p_run.add_argument("--runs-dir", default=RUNS_DIR_DEFAULT)
    p_run.add_argument("--only-id", default="")
    p_run.add_argument("--force", action="store_true")

    args = parser.parse_args()
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "enqueue":
        return cmd_enqueue(args)
    return cmd_run_queue(args)


if __name__ == "__main__":
    sys.exit(main())
