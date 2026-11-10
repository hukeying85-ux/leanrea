#!/usr/bin/env python3
"""Bootstrap & verify persistent Google Colab ADC credentials (PKCE S256 enabled).

Root cause of `Error 400: redirect_uri_mismatch` on `sdk.cloud.google.com/applicationdefaultauthcode.html`:
- Google's OAuth server gates the shared HTTPS copy-paste landing page
  `https://sdk.cloud.google.com/applicationdefaultauthcode.html` on PKCE
  (`code_challenge` + `code_challenge_method=S256`) + `state`.
- Requests to that `redirect_uri` WITHOUT `code_challenge` & `state` are rejected by
  Google with `Error 400: redirect_uri_mismatch`, whereas including PKCE S256 + `state`
  routes cleanly to `https://accounts.google.com/v3/signin/identifier`.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

# Public installed-app client shipped inside google_colab_cli/oauth_config.json
CLIENT_ID = "764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com"
CLIENT_SECRET = "d-FL95Q19q7MQmFpd7hHD0Ty"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
TOKENINFO_URI = "https://oauth2.googleapis.com/tokeninfo"
REMOTE_REDIRECT_URI = "https://sdk.cloud.google.com/applicationdefaultauthcode.html"

PUBLIC_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/colaboratory",
    "https://www.googleapis.com/auth/drive.file",
]

REQUIRED_SCOPE_MARKERS = ("userinfo.email", "colaboratory", "cloud-platform")
DEFAULT_PKCE_PATH = os.path.expanduser("~/.config/colab-cli/pkce_pending.json")


def generate_pkce_material() -> tuple[str, str, str]:
    """Return (code_verifier, code_challenge_s256, state)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    state = secrets.token_urlsafe(22)
    return verifier, challenge, state


def build_auth_url(
    *,
    code_challenge: str,
    state: str,
    redirect_uri: str = REMOTE_REDIRECT_URI,
) -> str:
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": " ".join(PUBLIC_SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    if redirect_uri == REMOTE_REDIRECT_URI:
        params["token_usage"] = "remote"
    return f"{AUTH_URI}?{urllib.parse.urlencode(params)}"


def extract_auth_code(raw: str) -> str:
    """Accept either a bare authorization code (`4/0A...`) or a pasted redirect URL."""
    s = raw.strip()
    if s.startswith(("http://", "https://")) or "code=" in s:
        parsed = urllib.parse.urlparse(s if "://" in s else f"http://localhost/?{s.lstrip('?')}")
        q = urllib.parse.parse_qs(parsed.query)
        if "code" in q and q["code"]:
            return q["code"][0].strip()
    return s


def _post_form(url: str, data: dict[str, str], timeout: int = 30) -> dict:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def exchange_code(
    raw_code: str,
    *,
    code_verifier: str = "",
    redirect_uri: str = REMOTE_REDIRECT_URI,
) -> tuple[dict, str]:
    clean_code = extract_auth_code(raw_code)
    if not clean_code:
        raise ValueError("Authorization code must not be empty.")
    form: dict[str, str] = {
        "code": clean_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    if code_verifier.strip():
        form["code_verifier"] = code_verifier.strip()

    tok = _post_form(TOKEN_URI, form)
    refresh_token = tok.get("refresh_token")
    access_token = tok.get("access_token", "")
    if not refresh_token:
        raise RuntimeError(
            "Google did not return a refresh_token. Re-open a fresh authorization URL "
            "(with prompt=consent & access_type=offline) and approve again."
        )
    adc_payload = {
        "type": "authorized_user",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    }
    return adc_payload, access_token


def inspect_access_token(access_token: str, timeout: int = 20) -> dict:
    url = f"{TOKENINFO_URI}?{urllib.parse.urlencode({'access_token': access_token})}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verify_adc_dict(adc: dict) -> dict:
    if adc.get("type") != "authorized_user" or not adc.get("refresh_token"):
        raise ValueError("Invalid ADC JSON: expected type='authorized_user' and non-empty 'refresh_token'.")
    tok = _post_form(
        TOKEN_URI,
        {
            "client_id": adc["client_id"],
            "client_secret": adc["client_secret"],
            "refresh_token": adc["refresh_token"],
            "grant_type": "refresh_token",
        },
    )
    info = inspect_access_token(tok["access_token"])
    scope_str = info.get("scope", "")
    missing = [m for m in REQUIRED_SCOPE_MARKERS if m not in scope_str]
    return {
        "ok": len(missing) == 0,
        "email": info.get("email", "<unknown>"),
        "expires_in": info.get("expires_in"),
        "scopes": scope_str.split(),
        "missing_scopes": missing,
    }


def check_auth_url_live(full_url: str) -> dict:
    """GET-only probe confirming Google routes the URL to Sign-In rather than /signin/oauth/error."""
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    req = urllib.request.Request(full_url, headers={"User-Agent": ua}, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        final_url = resp.geturl()
        body = resp.read(8192).decode("utf-8", errors="replace")
        status = resp.status
    accepted = ("/signin/oauth/error" not in final_url) and ("redirect_uri_mismatch" not in body) and (status == 200)
    return {
        "http_status": status,
        "accepted_by_google": accepted,
        "final_url_prefix": final_url[:180],
    }


def write_secure_json(path: str, payload: dict) -> str:
    full = os.path.abspath(os.path.expanduser(path))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    tmp = f"{full}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, full)
    return full


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap & verify persistent Google Colab ADC credentials."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--print-url",
        action="store_true",
        help="Generate PKCE S256 verifier + print the one-time Google OAuth authorization URL.",
    )
    group.add_argument(
        "--check-url",
        metavar="AUTH_URL",
        help="GET-only check against Google OAuth server that AUTH_URL reaches Sign-In.",
    )
    group.add_argument(
        "--exchange",
        metavar="AUTH_CODE",
        help="Exchange a one-time Google authorization code (or localhost URL) for an ADC JSON file.",
    )
    group.add_argument(
        "--exchange-env",
        metavar="ENV_VAR",
        help="Read the authorization code from ENV_VAR (avoids CLI argv exposure in CI).",
    )
    group.add_argument(
        "--verify",
        metavar="ADC_JSON_PATH",
        help="Refresh and verify an existing authorized_user ADC JSON file.",
    )
    parser.add_argument(
        "--redirect-uri",
        default=REMOTE_REDIRECT_URI,
        help=f"OAuth redirect URI (default: {REMOTE_REDIRECT_URI}; fallback: http://localhost:8085/).",
    )
    parser.add_argument(
        "--pkce-file",
        default=DEFAULT_PKCE_PATH,
        help=f"Where to save/load PKCE code_verifier (default: {DEFAULT_PKCE_PATH}).",
    )
    parser.add_argument(
        "--code-verifier-env",
        default="",
        help="Optional env var holding PKCE code_verifier (overrides --pkce-file).",
    )
    parser.add_argument(
        "--out",
        default=os.path.expanduser("~/.config/colab-cli/colab.adc.json"),
        help="Output path for the generated ADC JSON (default: ~/.config/colab-cli/colab.adc.json).",
    )
    args = parser.parse_args()

    if args.print_url:
        verifier, challenge, state = generate_pkce_material()
        url = build_auth_url(
            code_challenge=challenge,
            state=state,
            redirect_uri=args.redirect_uri,
        )
        write_secure_json(
            args.pkce_file,
            {
                "code_verifier": verifier,
                "code_challenge": challenge,
                "state": state,
                "redirect_uri": args.redirect_uri,
            },
        )
        print(url)
        return 0

    if args.check_url:
        res = check_auth_url_live(args.check_url)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["accepted_by_google"] else 2

    if args.verify:
        with open(os.path.expanduser(args.verify), "r", encoding="utf-8") as f:
            adc = json.load(f)
        report = verify_adc_dict(adc)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 2

    verifier = ""
    redirect_uri = args.redirect_uri
    if args.code_verifier_env and os.environ.get(args.code_verifier_env):
        verifier = os.environ[args.code_verifier_env].strip()
    elif os.path.exists(os.path.expanduser(args.pkce_file)):
        with open(os.path.expanduser(args.pkce_file), "r", encoding="utf-8") as pf:
            pkce_data = json.load(pf)
        verifier = pkce_data.get("code_verifier", "")
        redirect_uri = pkce_data.get("redirect_uri", redirect_uri)

    code = args.exchange if args.exchange else os.environ.get(args.exchange_env or "", "")
    adc_payload, access_token = exchange_code(
        code,
        code_verifier=verifier,
        redirect_uri=redirect_uri,
    )
    out_path = write_secure_json(args.out, adc_payload)
    summary: dict = {"saved_to": out_path, "type": "authorized_user"}
    if access_token:
        try:
            info = inspect_access_token(access_token)
            summary["email"] = info.get("email", "<unknown>")
            summary["scopes"] = info.get("scope", "").split()
        except Exception as exc:  # pragma: no cover
            summary["tokeninfo_note"] = str(exc)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
