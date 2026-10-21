"""The headless Chromium that every command runs in."""

from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Playwright

from uu_cli import paths

# Session cookies kept between runs, inside the (owner-only) session dir.
COOKIES_FILE = "cookies.json"

CHROMIUM_ARGS = [
    "--no-sandbox",
    # ── Single-process & memory reduction ──
    "--single-process",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-dev-shm-usage",
    # ── Strip non-essential features ──
    "--disable-extensions",
    "--disable-sync",
    "--disable-default-apps",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-features=TranslateUI,BackForwardCache",
    "--no-first-run",
]


def launch(pw: Playwright, session_dir: str | Path) -> BrowserContext:
    """Open the persistent browser profile in session_dir, with the last run's session restored."""
    ctx = pw.chromium.launch_persistent_context(
        str(session_dir),
        headless=True,
        no_viewport=True,
        args=CHROMIUM_ARGS,
    )
    restore_session(ctx, session_dir)
    return ctx


def restore_session(ctx: BrowserContext, session_dir: str | Path) -> None:
    """Put back the session cookies save_session kept; Chromium drops them when it closes."""
    try:
        cookies = json.loads((Path(session_dir) / COOKIES_FILE).read_text())
    except (OSError, ValueError):
        return
    now = time.time()
    live = [c for c in cookies if c.get("expires", -1) == -1 or c["expires"] > now]
    if live:
        ctx.add_cookies(live)


def save_session(ctx: BrowserContext, session_dir: str | Path) -> None:
    """Keep this run's session cookies (logins at UU and the platforms) for the next run.

    They are as good as a login until the server ends the session, so the file is owner-only.
    """
    try:
        session = [c for c in ctx.cookies() if c.get("expires", -1) == -1]
        paths.write_private(Path(session_dir) / COOKIES_FILE, json.dumps(session))
    except Exception:
        pass  # best effort: the next run just logs in again
