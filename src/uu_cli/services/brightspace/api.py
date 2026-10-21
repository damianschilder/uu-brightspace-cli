"""The Brightspace bearer token and authenticated calls to /d2l/api/."""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from typing import Any, Optional
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext

from uu_cli import paths

BASE_URL  = os.environ.get("BRIGHTSPACE_BASE_URL", "https://uu.brightspace.com").rstrip("/")


def load_token() -> dict | None:
    if not paths.TOKEN_FILE.exists():
        return None
    try:
        return json.loads(paths.TOKEN_FILE.read_text())
    except Exception:
        return None


def save_token(token: str) -> None:
    paths.write_private(paths.TOKEN_FILE, json.dumps({
        "token": token,
        "savedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expiresIn": 28800,
    }))


EXPIRED_MSG = ("ERROR: Brightspace token expired. "
               "Run 'brightspace-cli.py login' to get a new one.")


def token_expired(token: str, margin: int = 60) -> bool:
    """True if the token's JWT 'exp' claim is in the past (or within margin seconds)."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return claims["exp"] <= time.time() + margin
    except Exception:
        return False  # not a JWT we can read; let the API decide


def extract_token(ctx: BrowserContext) -> str | None:
    """
    Pull D2L.Fetch.Tokens from localStorage via Playwright.
    Handles cross-origin restrictions (skip pages where localStorage is inaccessible).
    Expired tokens left over in localStorage are ignored.
    """
    tok = _extract_token(ctx)
    return tok if tok and not token_expired(tok) else None


def _extract_token(ctx: BrowserContext) -> str | None:
    for page in ctx.pages:
        try:
            raw = page.evaluate(
                "localStorage.getItem('D2L.Fetch.Tokens') || ''"
            )
        except Exception:
            continue
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, dict) and v.get("access_token"):
                        return v["access_token"]
                if parsed.get("access_token"):
                    return parsed["access_token"]
        except Exception:
            pass
    return None


def refresh_token(ctx: BrowserContext) -> str | None:
    """Get a fresh token from a still-valid browser session (restored cookies), without a login."""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto(f"{BASE_URL}/d2l/home", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
    except Exception:
        return None
    if urlparse(page.url).hostname != urlparse(BASE_URL).hostname:
        return None
    token = extract_token(ctx)
    if token:
        save_token(token)
        print("[MAIN] Token refreshed from the saved session.", file=sys.stderr)
    return token


def api_fetch(ctx: BrowserContext, url: str, token: str,
              timeout: float = 20000) -> Optional[Any]:
    """GET a Brightspace /d2l/api/ endpoint via Playwright page JS (carries cookies)."""
    page = ctx.pages[0]
    try:
        data = page.evaluate(f"""
            async () => {{
                const r = await fetch(
                    "{url}",
                    {{ headers: {{ "Authorization": "Bearer {token}",
                                   "Accept": "application/json" }} }}
                );
                if (r.status === 401) return {{ "__unauthorized__": true }};
                const text = await r.text();
                if (r.status === 204 || !text.trim()) return null;
                try {{
                    return JSON.parse(text);
                }} catch {{
                    return null;
                }}
            }}
        """)
    except Exception as e:
        print(f"  ! API {url}: {e}", file=sys.stderr)
        return None
    if isinstance(data, dict) and data.get("__unauthorized__"):
        sys.exit(EXPIRED_MSG)
    return data


def get_token(ctx: BrowserContext, args) -> Optional[str]:
    token = (args.token
             or extract_token(ctx)
             or (load_token() or {}).get("token"))
    if not token:
        print("No token. Run 'brightspace-cli.py login' first.", file=sys.stderr)
        return None
    return token
