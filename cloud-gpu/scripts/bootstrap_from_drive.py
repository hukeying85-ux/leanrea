#!/usr/bin/env python3
"""Zero-leak credential loader from private Google Drive vault.json.

Supports two execution environments for any future Arena / Claude / Codex conversation:
1. Direct mode (`--mode direct`):
   Unpacks `colab_adc` -> `~/.gpu-relay/colab_adc.json` and `kaggle_api_token` -> `~/.gpu-relay/kaggle_token`
   (chmod 600) for environments with direct outbound internet access, then deletes any temporary input file.
2. Relay mode (`--mode encrypt-relay --pubkey cloud-gpu/relay_pubkey.pem`):
   Encrypts `vault.json` with RSA-4096 + AES-256-CBC + HMAC-SHA256 into `cloud-gpu/secrets/VAULT_JSON.enc`
   (and optional Google Drive resumable upload URIs) for Arena's network-restricted sandbox, then shreds
   the temporary plaintext input file so NOTHING plaintext ever touches Git or workspace snapshots.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


def encrypt_bytes(pubkey: str, payload: bytes, out_path: str) -> None:
    enc_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "encrypt_secret.py")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    subprocess.run(
        [sys.executable, enc_script, "encrypt", "--pubkey", pubkey, "--out", out_path],
        input=payload,
        check=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Hydrate Colab + Kaggle credentials from private Drive vault.json.")
    ap.add_argument("--vault-file", required=True, help="Temporary path to downloaded vault.json (deleted on exit unless --keep)")
    ap.add_argument("--mode", choices=["direct", "encrypt-relay"], required=True)
    ap.add_argument("--pubkey", default="cloud-gpu/relay_pubkey.pem", help="RSA public key for encrypt-relay mode")
    ap.add_argument("--secrets-dir", default="cloud-gpu/secrets", help="Output directory for .enc envelopes")
    ap.add_argument("--drive-result-uri", default="", help="One-time Google Drive resumable URI for execution report")
    ap.add_argument("--drive-upload-uri", default="", help="One-time Google Drive resumable URI for large model weights")
    ap.add_argument("--drive-endpoint-uri", default="", help="One-time Google Drive resumable URI for live tunnel endpoint")
    ap.add_argument("--keep", action="store_true", help="Do not delete --vault-file after processing")
    args = ap.parse_args()

    try:
        with open(args.vault_file, "r", encoding="utf-8") as f:
            raw_text = f.read()
        data = json.loads(raw_text)

        if args.mode == "direct":
            base = os.path.expanduser("~/.gpu-relay")
            os.makedirs(base, mode=0o700, exist_ok=True)
            if data.get("colab_adc"):
                cpath = os.path.join(base, "colab_adc.json")
                with open(cpath, "w", encoding="utf-8") as cf:
                    json.dump(data["colab_adc"], cf, indent=2)
                os.chmod(cpath, 0o600)
            if data.get("kaggle_api_token"):
                kpath = os.path.join(base, "kaggle_token")
                with open(kpath, "w", encoding="utf-8") as kf:
                    kf.write(str(data["kaggle_api_token"]).strip() + "\n")
                os.chmod(kpath, 0o600)
            print("Unpacked credentials to ~/.gpu-relay (chmod 600).")
        else:
            encrypt_bytes(
                args.pubkey,
                raw_text.encode("utf-8"),
                os.path.join(args.secrets_dir, "VAULT_JSON.enc"),
            )
            if args.drive_result_uri:
                encrypt_bytes(
                    args.pubkey,
                    args.drive_result_uri.encode("utf-8"),
                    os.path.join(args.secrets_dir, "DRIVE_RESULT_UPLOAD_URI.enc"),
                )
            if args.drive_upload_uri:
                encrypt_bytes(
                    args.pubkey,
                    args.drive_upload_uri.encode("utf-8"),
                    os.path.join(args.secrets_dir, "DRIVE_UPLOAD_URI.enc"),
                )
            if args.drive_endpoint_uri:
                encrypt_bytes(
                    args.pubkey,
                    args.drive_endpoint_uri.encode("utf-8"),
                    os.path.join(args.secrets_dir, "DRIVE_ENDPOINT_UPLOAD_URI.enc"),
                )
            print(f"Encrypted vault & Drive URIs into {args.secrets_dir}/.")
    finally:
        if not args.keep and os.path.exists(args.vault_file):
            os.remove(args.vault_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
