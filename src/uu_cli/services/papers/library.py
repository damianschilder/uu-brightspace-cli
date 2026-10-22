"""An article through UU's library proxy, in a browser window where you download it yourself.

UU's library reaches publishers through an EZproxy at utrechtuniversity.idm.oclc.org: its
login link logs you in with your Solis-id and then opens the article as a UU subscriber. The
CLI only builds that link and opens it in a window with your UU session; finding the PDF and
opening or downloading it is up to you, as on any other day. Every PDF you open or download
there is saved, so one window works for every publisher without code per publisher.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Download, Error as PlaywrightError, Response

from uu_cli import browser
from uu_cli.services.papers.articles import save_pdf

PROXY = "https://utrechtuniversity.idm.oclc.org"

# How long the window stays open for you to find the PDF.
WINDOW_TIMEOUT_S = 900


def proxy_url(article: str) -> str:
    """The proxy's login link for article; auth=uushibboleth is its "Universiteit Utrecht" choice
    (the other one is UMC Utrecht), so the proxy goes straight to UU's login."""
    return f"{PROXY}/login?auth=uushibboleth&url={article}"


def open_article(ctx: BrowserContext, article: str, out_dir: Path, name: str,
                 keep_open: bool = False) -> list[Path]:
    """Open article through the proxy in a window with ctx's session; returns the PDFs saved.

    The window closes once a PDF is saved (unless keep_open), when you close it, or after
    WINDOW_TIMEOUT_S. Its session goes back into ctx, so the next run skips the logins.
    """
    window = browser.open_window(ctx)
    found: list[Download | Response] = []  # saved from the loop below, not from the handlers
    window.on("page", lambda page: page.on("download", lambda d: found.append(d)))
    window.on("response", lambda r: found.append(r) if _is_pdf(r) else None)
    saved: list[Path] = []
    try:
        page = window.new_page()
        page.goto(proxy_url(article), wait_until="commit", timeout=60_000)
        deadline = time.monotonic() + WINDOW_TIMEOUT_S
        while time.monotonic() < deadline:
            while found:
                path = _save(found.pop(0), window, out_dir, name)
                if path and path not in saved:
                    saved.append(path)
                    print(f"Saved: {path}")
            if saved and not keep_open:
                break
            pages = [p for p in window.pages if not p.is_closed()]
            if not pages:
                break
            try:
                pages[0].wait_for_timeout(250)
            except PlaywrightError:
                pass  # closed meanwhile; the next round sees it
        else:
            print(f"[LIBRARY] Closing the window after {WINDOW_TIMEOUT_S // 60} minutes.",
                  file=sys.stderr)
        try:
            ctx.add_cookies(window.cookies())
        except PlaywrightError:
            pass  # you closed the browser itself; the next run just logs in again
    finally:
        try:
            window.browser.close()
        except PlaywrightError:
            pass
    return saved


def _is_pdf(response: Response) -> bool:
    content_type = response.headers.get("content-type", "")
    return response.status == 200 and content_type.split(";")[0].strip() == "application/pdf"


def _save(item: Download | Response, window: BrowserContext, out_dir: Path, name: str) -> Path | None:
    """Save a download or a PDF that opened in a tab; None when it turns out not to be a PDF."""
    try:
        if isinstance(item, Download):
            data = Path(item.path()).read_bytes()
        else:
            try:
                data = item.body()
            except PlaywrightError:  # shown in Chromium's PDF viewer: fetch it once more
                data = window.request.get(item.url).body()
    except (PlaywrightError, OSError, TypeError):
        return None
    return save_pdf(out_dir, data, name) if data.startswith(b"%PDF") else None
