#!/usr/bin/env python3
"""Unified Colab & Kaggle Cloud GPU Controller (Local CLI + GitHub Actions Relay).

Subcommands:
  doctor     Inspect local & relay credential readiness.
  route      Explain which provider (Colab vs Kaggle) best fits a workload.
  enqueue    Add a job (probe | run | deploy | status | output) to cloud-gpu/jobs/queue.json.
  run-queue  Execute pending jobs in queue.json (runs locally or inside gpu-relay.yml).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

QUEUE_DEFAULT = "cloud-gpu/jobs/queue.json"
RUNS_DIR_DEFAULT = "cloud-gpu/runs"
MAX_GIT_FILE_BYTES = 2 * 1024 * 1024  # Keep git artifacts <= 2 MiB; big weights go to Drive


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mask_email(email: str) -> str:
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    head = local[:2] if len(local) >= 2 else local[:1]
    return f"{head}***@{domain}"


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


def resolve_colab_env() -> tuple[dict[str, str], str | None]:
    """Build environment with GOOGLE_APPLICATION_CREDENTIALS if available."""
    env = os.environ.copy()
    adc_path = env.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if adc_path and os.path.exists(os.path.expanduser(adc_path)):
        full = os.path.abspath(os.path.expanduser(adc_path))
        env["GOOGLE_APPLICATION_CREDENTIALS"] = full
        return env, full

    candidates = [
        os.path.expanduser("~/.gpu-relay/colab_adc.json"),
        os.path.expanduser("~/.config/colab-cli/colab.adc.json"),
        os.path.expanduser("~/.config/gcloud/application_default_credentials.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            env["GOOGLE_APPLICATION_CREDENTIALS"] = c
            return env, c
    return env, None


def resolve_kaggle_env() -> tuple[dict[str, str], str | None]:
    """Configure Kaggle credentials from env or vault files."""
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
    """Resolve Kaggle username via kagglesdk / KaggleApi introspection."""
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


def route_decision(vram_gb: int, hours: float, mode: str, gpus: int) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []

    # Kaggle free tier: NvidiaTeslaT4 = 2 x 16GB T4 (32GB total, 16GB per card), 12h cap, 30h/wk
    if vram_gb > 16 and gpus == 1:
        excluded.append(
            {"provider": "kaggle", "reason": f"Needs {vram_gb}GB on a single GPU; Kaggle free T4 has 16GB per card (2x16GB total)."}
        )
    elif hours > 12:
        excluded.append(
            {"provider": "kaggle", "reason": f"Runtime {hours}h exceeds Kaggle's 12h session cap (use checkpoint handover)."}
        )
    else:
        score = 80
        reasons = ["NvidiaTeslaT4 gives 2x16GB T4 (32GB total), 30h/week free, up to 12h continuous run"]
        if gpus >= 2 or hours >= 2.0:
            score += 20
            reasons.append("ideal for multi-GPU DataParallel/DDP or jobs >= 2h without holding CI runners")
        if mode == "deploy" and hours >= 1.0:
            score += 15
            reasons.append("async kernel keeps HTTPS tunnel alive up to 12h with zero Actions minutes")
        candidates.append({"provider": "kaggle", "accelerator": "NvidiaTeslaT4", "score": score, "reason": "; ".join(reasons)})

    # Colab: T4 (16GB free), L4 (24GB Pro), A100 (40/80GB Pro)
    if gpus > 1:
        excluded.append({"provider": "colab", "reason": f"Requested {gpus} GPUs; Colab VMs expose 1 GPU per session."})
    elif hours > 12:
        excluded.append({"provider": "colab", "reason": f"Runtime {hours}h exceeds Colab's 12h cap."})
    else:
        acc = "T4" if vram_gb <= 16 else ("L4" if vram_gb <= 24 else "A100")
        tier_note = "free/Pro" if acc == "T4" else "requires Colab Pro/CCU"
        score = 85 if (hours < 2.0 and gpus == 1 and vram_gb <= 16) else 70
        if vram_gb > 16:
            score = 90  # Only Colab Pro L4/A100 fits >16GB single-card
        candidates.append(
            {
                "provider": "colab",
                "accelerator": acc,
                "score": score,
                "reason": f"{acc} ({tier_note}) provisions in ~10s via `colab --auth=adc`, persistent kernel state & fast iterative debug",
            }
        )

    candidates.sort(key=lambda x: -x["score"])
    return {
        "recommended": candidates[0] if candidates else None,
        "candidates": candidates,
        "excluded": excluded,
    }


def execute_probe(job: dict[str, Any], run_dir: str) -> dict[str, Any]:
    colab_env, adc_file = resolve_colab_env()
    kaggle_env, kag_src = resolve_kaggle_env()

    report: dict[str, Any] = {
        "job_id": job["id"],
        "provider": "probe",
        "timestamp_utc": utc_now(),
        "python_version": sys.version.split()[0],
        "tools": {
            "colab_cli": shutil.which("colab"),
            "kaggle_cli": shutil.which("kaggle"),
        },
        "colab": {"configured": bool(adc_file), "credential_source": adc_file, "authenticated": False},
        "kaggle": {"configured": bool(kag_src), "credential_source": kag_src, "authenticated": False},
    }

    if adc_file and shutil.which("colab"):
        # Verify token via colab_auth_bootstrap + colab sessions
        boot_script = os.path.join(os.path.dirname(__file__), "colab_auth_bootstrap.py")
        ver = run_cmd([sys.executable, boot_script, "--verify", adc_file], env=colab_env, timeout=30)
        if ver.returncode == 0:
            vinfo = json.loads(ver.stdout)
            report["colab"]["account"] = mask_email(vinfo.get("email", ""))
            report["colab"]["scopes_ok"] = vinfo.get("ok", False)
        sess = run_cmd(["colab", "--auth=adc", "sessions"], env=colab_env, timeout=45)
        usage = run_cmd(["colab", "--auth=adc", "usage"], env=colab_env, timeout=45)
        report["colab"]["authenticated"] = sess.returncode == 0
        report["colab"]["sessions_output"] = (sess.stdout or sess.stderr).strip()[:500]
        if usage.returncode == 0:
            report["colab"]["usage_output"] = usage.stdout.strip()[:500]
    elif job.get("check_oauth_url"):
        boot_script = os.path.join(os.path.dirname(__file__), "colab_auth_bootstrap.py")
        chk = run_cmd([sys.executable, boot_script, "--check-url", job["check_oauth_url"]], env=colab_env, timeout=30)
        if chk.stdout.strip():
            report["colab"]["oauth_url_check"] = json.loads(chk.stdout)

    if kag_src and shutil.which("kaggle"):
        try:
            uname = get_kaggle_username(kaggle_env)
            report["kaggle"]["authenticated"] = True
            report["kaggle"]["username"] = uname
            klist = run_cmd(
                ["kaggle", "kernels", "list", "-m", "--page-size", "5", "-v"],
                env=kaggle_env,
                timeout=45,
            )
            if klist.returncode == 0:
                report["kaggle"]["recent_kernels_csv"] = klist.stdout.strip()[:600]
        except Exception as exc:
            report["kaggle"]["error"] = str(exc)

    report["status"] = "completed"
    out_file = os.path.join(run_dir, "result.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return report


def execute_colab_job(
    job: dict[str, Any],
    run_dir: str,
    on_endpoint_ready_cmd: str | None = None,
) -> dict[str, Any]:
    colab_env, adc_file = resolve_colab_env()
    if not adc_file:
        raise RuntimeError(
            "Colab credentials not configured. Set GitHub Secret `COLAB_ADC_JSON` or "
            "encrypt a one-time OAuth code into `cloud-gpu/secrets/COLAB_OAUTH_CODE.enc`."
        )
    if not shutil.which("colab"):
        raise RuntimeError("`colab` CLI not installed (requires Python >=3.12 + `pip install google-colab-cli`).")

    mode = job.get("mode", "run")
    acc = job.get("accelerator", "T4")
    script_path = job["script_path"]
    script_args = job.get("script_args", [])
    extra_pip = job.get("extra_pip", [])
    session_name = re.sub(r"[^a-z0-9-]", "-", job["id"].lower())[:24].strip("-") or "dljob"
    keep_session = bool(job.get("keep_session", False))

    new_cmd = ["colab", "--auth=adc", "new", "-s", session_name]
    if acc and acc.upper() not in ("CPU", "NONE"):
        if acc.lower().startswith("v5") or acc.lower().startswith("v6"):
            new_cmd += ["--tpu", acc]
        else:
            new_cmd += ["--gpu", acc]

    started = time.time()
    allocated = False
    try:
        alloc = run_cmd(new_cmd, env=colab_env, timeout=180)
        if alloc.returncode != 0:
            raise RuntimeError(f"colab new failed: {(alloc.stderr or alloc.stdout).strip()}")
        allocated = True

        if extra_pip:
            inst = run_cmd(["colab", "--auth=adc", "install", "-s", session_name, *extra_pip], env=colab_env, timeout=600)
            if inst.returncode != 0:
                raise RuntimeError(f"colab install failed: {(inst.stderr or inst.stdout).strip()}")

        with open(script_path, "r", encoding="utf-8") as sf:
            script_src = sf.read()

        # Build remote wrapper so sys.argv and optional upload URIs work seamlessly inside /content
        injected_env: dict[str, str] = {}
        for k in ("DRIVE_UPLOAD_URI", "DRIVE_ENDPOINT_UPLOAD_URI"):
            if os.environ.get(k):
                injected_env[k] = os.environ[k]

        if mode == "deploy" and "--detach" not in script_args:
            effective_args = [*script_args, "--detach"]
        else:
            effective_args = list(script_args)

        wrapper_code = (
            "import json, os, sys, runpy\n"
            f"os.environ.update({repr(injected_env)})\n"
            "os.makedirs('/content/outputs', exist_ok=True)\n"
            f"with open('/content/_job_entry.py', 'w', encoding='utf-8') as _f:\n"
            f"    _f.write({repr(script_src)})\n"
            f"sys.argv = ['/content/_job_entry.py', *{repr([str(a) for a in effective_args])}]\n"
            "runpy.run_path('/content/_job_entry.py', run_name='__main__')\n"
            "if os.path.exists('/content/outputs/metrics.json'):\n"
            "    with open('/content/outputs/metrics.json', 'r', encoding='utf-8') as _mf:\n"
            "        print('COLAB_METRICS_JSON=' + json.dumps(json.load(_mf), ensure_ascii=False), flush=True)\n"
        )

        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
            tf.write(wrapper_code)
            wrapper_path = tf.name

        try:
            ex = run_cmd(
                ["colab", "--auth=adc", "exec", "-s", session_name, "-f", wrapper_path, "--timeout", "0"],
                env=colab_env,
                timeout=int(job.get("timeout_sec", 3600)),
            )
        finally:
            if os.path.exists(wrapper_path):
                os.remove(wrapper_path)

        stdout_log = ex.stdout or ""
        stderr_log = ex.stderr or ""
        with open(os.path.join(run_dir, "colab_exec.log"), "w", encoding="utf-8") as lf:
            lf.write(stdout_log)
            if stderr_log:
                lf.write("\n--- STDERR ---\n" + stderr_log)

        if ex.returncode != 0:
            raise RuntimeError(f"colab exec failed (exit {ex.returncode}): {(stderr_log or stdout_log)[-800:]}")

        endpoint_data = None
        metrics_data = None
        for line in stdout_log.splitlines():
            if line.startswith("DEPLOY_ENDPOINT_JSON="):
                endpoint_data = json.loads(line.split("=", 1)[1])
                ep_file = os.path.join(run_dir, "endpoint.json")
                with open(ep_file, "w", encoding="utf-8") as ef:
                    json.dump(endpoint_data, ef, ensure_ascii=False, indent=2)
                    ef.write("\n")
                if on_endpoint_ready_cmd:
                    subprocess.run(on_endpoint_ready_cmd, shell=True, check=False)
            elif line.startswith("COLAB_METRICS_JSON="):
                metrics_data = json.loads(line.split("=", 1)[1])
                m_file = os.path.join(run_dir, "metrics.json")
                with open(m_file, "w", encoding="utf-8") as mf:
                    json.dump(metrics_data, mf, ensure_ascii=False, indent=2)
                    mf.write("\n")

        # Pull small JSON summaries from /content/outputs if not already streamed over stdout
        for remote_name in ("metrics.json", "endpoint.json"):
            dst = os.path.join(run_dir, remote_name)
            if not os.path.exists(dst):
                dl = run_cmd(
                    ["colab", "--auth=adc", "download", "-s", session_name, f"/content/outputs/{remote_name}", dst],
                    env=colab_env,
                    timeout=60,
                )
                if dl.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > MAX_GIT_FILE_BYTES:
                    os.remove(dst)

        # Hold live deployment tunnel open for requested serve_minutes before safe VM teardown
        serve_minutes = float(job.get("serve_minutes", 15.0))
        if mode == "deploy" and not keep_session and serve_minutes > 0:
            hold_until = time.time() + serve_minutes * 60.0
            while time.time() < hold_until:
                time.sleep(min(30.0, max(1.0, hold_until - time.time())))
                ping = subprocess.run(
                    ["colab", "--auth=adc", "exec", "-s", session_name],
                    input="import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:7860/health', timeout=5).read().decode())\n",
                    text=True,
                    capture_output=True,
                    env=colab_env,
                    timeout=30,
                    check=False,
                )
                if ping.returncode != 0:
                    break

        res_payload = {
            "job_id": job["id"],
            "provider": "colab",
            "mode": mode,
            "accelerator": acc,
            "session_name": session_name,
            "kept_alive": keep_session,
            "status": "serving_detached" if (mode == "deploy" and keep_session) else "completed",
            "metrics": metrics_data,
            "endpoint": endpoint_data,
            "wall_sec": round(time.time() - started, 2),
            "finished_at_utc": utc_now(),
        }
        with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as rf:
            json.dump(res_payload, rf, ensure_ascii=False, indent=2)
            rf.write("\n")
        return res_payload
    finally:
        if allocated and not keep_session:
            run_cmd(["colab", "--auth=adc", "stop", "-s", session_name], env=colab_env, timeout=60)


def execute_kaggle_job(job: dict[str, Any], run_dir: str) -> dict[str, Any]:
    kaggle_env, kag_src = resolve_kaggle_env()
    if not kag_src:
        raise RuntimeError(
            "Kaggle credentials not configured. Set GitHub Secret `KAGGLE_API_TOKEN` "
            "(from https://www.kaggle.com/settings/api) or encrypt `KAGGLE_API_TOKEN.enc`."
        )
    if not shutil.which("kaggle"):
        raise RuntimeError("`kaggle` CLI not installed (`pip install kaggle six`).")

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
        tmp_out = tempfile.mkdtemp(prefix="kag_out_")
        try:
            out = run_cmd(["kaggle", "kernels", "output", kernel_ref, "-p", tmp_out, "-o"], env=kaggle_env, timeout=300)
            copied = _copy_small_outputs(tmp_out, run_dir)
            payload = {
                "job_id": job["id"],
                "provider": "kaggle",
                "mode": "output",
                "kernel_ref": kernel_ref,
                "copied_files": copied,
                "cli_output": (out.stdout or out.stderr).strip()[:600],
                "fetched_at_utc": utc_now(),
            }
            with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as rf:
                json.dump(payload, rf, ensure_ascii=False, indent=2)
                rf.write("\n")
            return payload
        finally:
            shutil.rmtree(tmp_out, ignore_errors=True)

    acc = job.get("accelerator", "NvidiaTeslaT4")
    enable_gpu = acc.upper() not in ("CPU", "NONE") and not acc.lower().startswith("tpu")
    script_path = job["script_path"]
    script_args = job.get("script_args", [])
    extra_pip = job.get("extra_pip", [])

    with open(script_path, "r", encoding="utf-8") as sf:
        script_src = sf.read()

    injected_env: dict[str, str] = {}
    for k in ("DRIVE_UPLOAD_URI", "DRIVE_ENDPOINT_UPLOAD_URI"):
        if os.environ.get(k):
            injected_env[k] = os.environ[k]

    stage_dir = tempfile.mkdtemp(prefix="kag_push_")
    try:
        entry_py = os.path.join(stage_dir, "entry_main.py")
        pip_snippet = (
            f"import subprocess, sys\nsubprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *{repr(extra_pip)}])\n"
            if extra_pip
            else ""
        )
        wrapper = (
            "import os, sys, runpy\n"
            f"{pip_snippet}"
            f"os.environ.update({repr(injected_env)})\n"
            f"with open('/tmp/_payload.py', 'w', encoding='utf-8') as _f:\n"
            f"    _f.write({repr(script_src)})\n"
            f"sys.argv = ['/tmp/_payload.py', *{repr([str(a) for a in script_args])}]\n"
            "runpy.run_path('/tmp/_payload.py', run_name='__main__')\n"
        )
        with open(entry_py, "w", encoding="utf-8") as ef:
            ef.write(wrapper)

        title = re.sub(r"[^A-Za-z0-9 -]", " ", slug.replace("-", " ")).strip() or f"gpu job {job['id']}"
        # Ensure title slugifies back to `slug` per Kaggle's title<->slug rule
        title = " ".join(slug.split("-"))
        metadata = {
            "id": kernel_ref,
            "title": title,
            "code_file": "entry_main.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": "true",
            "enable_gpu": "true" if enable_gpu else "false",
            "enable_internet": "true",
            "machine_shape": acc if acc.upper() not in ("CPU", "NONE") else "",
            "dataset_sources": job.get("dataset_sources", []),
            "competition_sources": job.get("competition_sources", []),
            "kernel_sources": job.get("kernel_sources", []),
            "model_sources": job.get("model_sources", []),
        }
        with open(os.path.join(stage_dir, "kernel-metadata.json"), "w", encoding="utf-8") as mf:
            json.dump(metadata, mf, indent=2)

        push_cmd = ["kaggle", "kernels", "push", "-p", stage_dir]
        if acc and acc.upper() not in ("CPU", "NONE"):
            push_cmd += ["--accelerator", acc]
        pushed = run_cmd(push_cmd, env=kaggle_env, timeout=120)
        if pushed.returncode != 0:
            raise RuntimeError(f"kaggle kernels push failed: {(pushed.stderr or pushed.stdout).strip()}")
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)

    wait_for_completion = bool(job.get("wait", mode == "run"))
    copied_files: list[str] = []
    final_status = "pushed_async"

    if wait_for_completion:
        poll_timeout = int(job.get("timeout_sec", 3600))
        deadline = time.time() + poll_timeout
        while time.time() < deadline:
            time.sleep(20)
            st = run_cmd(["kaggle", "kernels", "status", kernel_ref], env=kaggle_env, timeout=45)
            txt = (st.stdout or st.stderr).lower()
            if "complete" in txt:
                final_status = "completed"
                break
            if "error" in txt or "cancel" in txt:
                final_status = "failed"
                break
        tmp_out = tempfile.mkdtemp(prefix="kag_out_")
        try:
            run_cmd(["kaggle", "kernels", "output", kernel_ref, "-p", tmp_out, "-o"], env=kaggle_env, timeout=300)
            copied_files = _copy_small_outputs(tmp_out, run_dir)
        finally:
            shutil.rmtree(tmp_out, ignore_errors=True)
        if final_status == "failed":
            raise RuntimeError(f"Kaggle kernel {kernel_ref} ended with error; inspect logs in {run_dir}.")

    payload = {
        "job_id": job["id"],
        "provider": "kaggle",
        "mode": mode,
        "accelerator": acc,
        "kernel_ref": kernel_ref,
        "kernel_url": f"https://www.kaggle.com/code/{kernel_ref}",
        "status": final_status,
        "copied_files": copied_files,
        "push_output": (pushed.stdout or "").strip()[:500],
        "updated_at_utc": utc_now(),
    }
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as rf:
        json.dump(payload, rf, ensure_ascii=False, indent=2)
        rf.write("\n")
    return payload


def _copy_small_outputs(src_root: str, dst_dir: str) -> list[str]:
    copied: list[str] = []
    for root, _, files in os.walk(src_root):
        for fn in files:
            full = os.path.join(root, fn)
            if os.path.getsize(full) <= MAX_GIT_FILE_BYTES and not fn.endswith((".pt", ".pth", ".safetensors", ".onnx", ".gguf")):
                rel = os.path.relpath(full, src_root).replace(os.sep, "_")
                shutil.copy2(full, os.path.join(dst_dir, rel))
                copied.append(rel)
    return sorted(copied)


def cmd_doctor(_: argparse.Namespace) -> int:
    _, adc = resolve_colab_env()
    _, kag = resolve_kaggle_env()
    pubkey = os.path.exists("cloud-gpu/relay_pubkey.pem")
    info = {
        "python": sys.version.split()[0],
        "local_colab_cli": shutil.which("colab"),
        "local_kaggle_cli": shutil.which("kaggle"),
        "gh_cli": shutil.which("gh"),
        "local_colab_credentials": adc,
        "local_kaggle_credentials": kag,
        "relay_pubkey_ready": pubkey,
        "recommended_execution_channel": (
            "local-direct" if (shutil.which("colab") or shutil.which("kaggle")) and (adc or kag) else "github-actions-relay"
        ),
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    res = route_decision(args.vram, args.hours, args.mode, args.gpus)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["recommended"] else 1


def cmd_enqueue(args: argparse.Namespace) -> int:
    qpath = args.queue
    os.makedirs(os.path.dirname(os.path.abspath(qpath)), exist_ok=True)
    queue: dict[str, Any] = {"jobs": []}
    if os.path.exists(qpath):
        with open(qpath, "r", encoding="utf-8") as f:
            queue = json.load(f)

    provider = args.provider
    acc = args.accelerator
    if provider == "auto":
        decision = route_decision(args.vram, args.hours, args.mode, args.gpus)
        if not decision["recommended"]:
            raise RuntimeError("No free/configured provider matches requested hardware constraints.")
        provider = decision["recommended"]["provider"]
        acc = acc or decision["recommended"]["accelerator"]

    if not acc:
        acc = "NvidiaTeslaT4" if provider == "kaggle" else ("T4" if provider == "colab" else "")

    job_id = args.id or f"{provider}-{dt.datetime.now(dt.timezone.utc).strftime('%m%d-%H%M%S')}"
    job: dict[str, Any] = {
        "id": job_id,
        "provider": provider,
        "mode": args.mode,
        "accelerator": acc,
        "script_path": args.script or "",
        "script_args": shlex.split(args.script_args) if args.script_args else [],
        "extra_pip": shlex.split(args.extra_pip) if args.extra_pip else [],
        "serve_minutes": args.serve_minutes,
        "wait": not args.async_push,
        "status": "pending",
        "created_at_utc": utc_now(),
    }
    if args.kernel_slug:
        job["kernel_slug"] = args.kernel_slug

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
            elif prov == "colab":
                res = execute_colab_job(job, run_dir, on_endpoint_ready_cmd=args.on_endpoint_ready_cmd)
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
    parser = argparse.ArgumentParser(description="Colab & Kaggle Unified GPU Controller.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Check local & relay credential readiness")

    p_route = sub.add_parser("route", help="Recommend Colab vs Kaggle for a job")
    p_route.add_argument("--vram", type=int, default=16, help="Required VRAM per GPU in GB")
    p_route.add_argument("--hours", type=float, default=1.0, help="Estimated runtime in hours")
    p_route.add_argument("--gpus", type=int, default=1, help="Number of GPUs requested")
    p_route.add_argument("--mode", choices=["run", "deploy"], default="run")

    p_enq = sub.add_parser("enqueue", help="Enqueue a GPU job into cloud-gpu/jobs/queue.json")
    p_enq.add_argument("--queue", default=QUEUE_DEFAULT)
    p_enq.add_argument("--id", help="Explicit job ID")
    p_enq.add_argument("--provider", choices=["auto", "probe", "colab", "kaggle"], default="auto")
    p_enq.add_argument("--mode", choices=["probe", "run", "deploy", "status", "output"], default="run")
    p_enq.add_argument("--accelerator", default="")
    p_enq.add_argument("--script", default="")
    p_enq.add_argument("--script-args", default="")
    p_enq.add_argument("--extra-pip", default="")
    p_enq.add_argument("--serve-minutes", type=float, default=15.0)
    p_enq.add_argument("--async-push", action="store_true", help="Return immediately after Kaggle push")
    p_enq.add_argument("--kernel-slug", default="")
    p_enq.add_argument("--vram", type=int, default=16)
    p_enq.add_argument("--hours", type=float, default=1.0)
    p_enq.add_argument("--gpus", type=int, default=1)

    p_run = sub.add_parser("run-queue", help="Execute pending jobs in queue.json")
    p_run.add_argument("--queue", default=QUEUE_DEFAULT)
    p_run.add_argument("--runs-dir", default=RUNS_DIR_DEFAULT)
    p_run.add_argument("--only-id", default="")
    p_run.add_argument("--force", action="store_true")
    p_run.add_argument("--on-endpoint-ready-cmd", default="")

    args = parser.parse_args()
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "route":
        return cmd_route(args)
    if args.cmd == "enqueue":
        return cmd_enqueue(args)
    return cmd_run_queue(args)


if __name__ == "__main__":
    sys.exit(main())
