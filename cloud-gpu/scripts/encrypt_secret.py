#!/usr/bin/env python3
"""Hybrid RSA-4096-OAEP-SHA256 + AES-256-CBC envelope tool (pure stdlib + openssl CLI).

Why hybrid instead of raw `openssl pkeyutl`:
- RSA-4096 with OAEP-SHA256 caps plaintext at 446 bytes (512 - 2*32 - 2).
- `COLAB_ADC_JSON` or Google Drive resumable upload URIs easily exceed 446 bytes.
- Hybrid encryption wraps a fresh 32-byte AES key + 16-byte IV under RSA-OAEP-SHA256
  and encrypts arbitrary-size secrets with AES-256-CBC + HMAC-SHA256 (Encrypt-then-MAC).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys


def _run_openssl(args: list[str], data: bytes) -> bytes:
    proc = subprocess.run(
        ["openssl", *args],
        input=data,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"openssl {' '.join(args[:3])} failed: {err}")
    return proc.stdout


def encrypt_bytes(plaintext: bytes, pubkey_pem_path: str) -> dict:
    aes_key = secrets.token_bytes(32)
    mac_key = secrets.token_bytes(32)
    iv = secrets.token_bytes(16)
    key_material = aes_key + mac_key + iv  # 80 bytes << 446-byte RSA-4096 OAEP limit

    wrapped_key = _run_openssl(
        [
            "pkeyutl",
            "-encrypt",
            "-pubin",
            "-inkey",
            pubkey_pem_path,
            "-pkeyopt",
            "rsa_padding_mode:oaep",
            "-pkeyopt",
            "rsa_oaep_md:sha256",
        ],
        key_material,
    )
    ciphertext = _run_openssl(
        [
            "enc",
            "-aes-256-cbc",
            "-K",
            aes_key.hex(),
            "-iv",
            iv.hex(),
            "-nosalt",
        ],
        plaintext,
    )
    tag = hmac.new(mac_key, wrapped_key + iv + ciphertext, hashlib.sha256).digest()
    return {
        "v": 1,
        "alg": "RSA4096-OAEP-SHA256+AES256-CBC-HMAC-SHA256",
        "ek": base64.b64encode(wrapped_key).decode("ascii"),
        "ct": base64.b64encode(ciphertext).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
    }


def decrypt_envelope(env: dict, privkey_pem_path: str) -> bytes:
    if env.get("v") != 1:
        raise ValueError(f"Unsupported envelope version: {env.get('v')}")
    wrapped_key = base64.b64decode(env["ek"])
    ciphertext = base64.b64decode(env["ct"])
    expected_tag = base64.b64decode(env["tag"])

    key_material = _run_openssl(
        [
            "pkeyutl",
            "-decrypt",
            "-inkey",
            privkey_pem_path,
            "-pkeyopt",
            "rsa_padding_mode:oaep",
            "-pkeyopt",
            "rsa_oaep_md:sha256",
        ],
        wrapped_key,
    )
    if len(key_material) != 80:
        raise ValueError("Invalid unwrapped key material length.")
    aes_key = key_material[:32]
    mac_key = key_material[32:64]
    iv = key_material[64:80]

    actual_tag = hmac.new(mac_key, wrapped_key + iv + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(actual_tag, expected_tag):
        raise ValueError("HMAC verification failed: envelope tampered or wrong key.")

    return _run_openssl(
        [
            "enc",
            "-d",
            "-aes-256-cbc",
            "-K",
            aes_key.hex(),
            "-iv",
            iv.hex(),
            "-nosalt",
        ],
        ciphertext,
    )


def cmd_encrypt(args: argparse.Namespace) -> int:
    if args.from_file:
        with open(args.from_file, "rb") as f:
            raw = f.read()
    elif args.from_env:
        val = os.environ.get(args.from_env, "")
        if not val:
            raise ValueError(f"Environment variable {args.from_env} is empty.")
        raw = val.encode("utf-8")
    else:
        raw = sys.stdin.buffer.read()

    if not raw.strip():
        raise ValueError("Refusing to encrypt empty secret payload.")

    envelope = encrypt_bytes(raw.strip(), args.pubkey)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2)
        f.write("\n")
    print(f"Encrypted ({len(raw.strip())} bytes) -> {args.out}")
    return 0


def cmd_decrypt(args: argparse.Namespace) -> int:
    with open(args.infile, "r", encoding="utf-8") as f:
        envelope = json.load(f)
    plaintext = decrypt_envelope(envelope, args.privkey)
    if args.out:
        full = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(plaintext)
        os.chmod(full, 0o600)
    else:
        sys.stdout.buffer.write(plaintext)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Hybrid RSA+AES secret envelope helper.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_enc = sub.add_parser("encrypt", help="Encrypt secret with relay_pubkey.pem")
    p_enc.add_argument("--pubkey", default="cloud-gpu/relay_pubkey.pem")
    p_enc.add_argument("--out", required=True, help="Output .enc JSON path")
    src = p_enc.add_mutually_exclusive_group()
    src.add_argument("--from-file", help="Read plaintext from file")
    src.add_argument("--from-env", help="Read plaintext from environment variable")

    p_dec = sub.add_parser("decrypt", help="Decrypt .enc envelope with private key")
    p_dec.add_argument("--privkey", required=True)
    p_dec.add_argument("--in", dest="infile", required=True)
    p_dec.add_argument("--out", help="Optional output file (chmod 600); else stdout")

    args = parser.parse_args()
    return cmd_encrypt(args) if args.cmd == "encrypt" else cmd_decrypt(args)


if __name__ == "__main__":
    sys.exit(main())
