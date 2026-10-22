"""The headless Chromium that every command runs in."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import BrowserContext, Playwright

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
    """Open the persistent browser profile in session_dir."""
    return pw.chromium.launch_persistent_context(
        str(session_dir),
        headless=True,
        no_viewport=True,
        args=CHROMIUM_ARGS,
    )
