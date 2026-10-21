"""The headless Chromium that every command runs in."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Error as PlaywrightError, Playwright, Route

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

# The visible window of --auth browser: an ordinary Chromium, so UU's pages behave as they do for you.
WINDOW_ARGS = ["--no-first-run", "--disable-sync", "--disable-default-apps", "--disable-extensions"]


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


def open_window(ctx: BrowserContext) -> BrowserContext:
    """A visible browser window that starts with ctx's cookies, to log in by hand.

    Close it with `.browser.close()`; ctx.add_cookies(window.cookies()) takes its session over.
    """
    window = ctx.browser.browser_type.launch(headless=False, args=WINDOW_ARGS)
    win = window.new_context(no_viewport=True)
    win.add_cookies(ctx.cookies())
    return win


def own_files_only(ctx: BrowserContext, host: str) -> None:
    """On host's pages, load only host's own files; leaving for another site (a login) still works.

    Konjoin's pages wait for third-party scripts and fonts (cdn.polyfill.io, cdnjs, Google
    Fonts) before they count as loaded. The CLI needs none of them, and when one hangs, the page
    hangs past every timeout. cdn.polyfill.io is also the domain that served malware in 2024; it
    has no business running next to a login session.
    """
    def route(r: Route) -> None:
        req = r.request
        try:
            on_host = urlparse(req.frame.url).hostname == host
        except PlaywrightError:
            on_host = False  # not from a page (a service worker): leave it alone
        if on_host and not req.is_navigation_request() and urlparse(req.url).hostname != host:
            r.abort()
        else:
            r.fallback()

    ctx.route("**/*", route)


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
