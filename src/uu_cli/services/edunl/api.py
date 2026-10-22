"""edu.nl's own pages under /manage/, logged in through SURFconext.

edu.nl has no API: the CLI uses the same form and overview you use in a browser, one link per
command. Its pages as seen on 22-10-2026: the "Shorten a link" form (short_url[longUrl] and a
CSRF token) sends you to /manage/url/<code>/show, which has the new link and a form for a label;
/manage/page/<n> lists your links in a table, with ?filterValue= for its search box.
"""

from __future__ import annotations

import os
import re
import time
from urllib.parse import urlencode, urlparse

from playwright.sync_api import BrowserContext, Error as PlaywrightError, Page

BASE_URL = os.environ.get("UU_EDUNL_URL", "https://edu.nl").rstrip("/")
MANAGE_URL = f"{BASE_URL}/manage/"
HOST = urlparse(BASE_URL).hostname

# How long a page may take to settle: the form's answer, or a redirect to SURFconext.
SETTLE_S = 15

# Your links, row by row, from the overview's table.
LINKS = """() => [...document.querySelectorAll('tbody[data-test="links"] tr')].map(tr => {
    const td = tr.querySelectorAll('td');  // actions, short link, date, original, label
    const original = td[3] && td[3].querySelector('a');
    return {
        short: (tr.querySelector('[data-clipboard-text]') || {}).dataset?.clipboardText || '',
        clicks: Number((tr.querySelector('th') || {}).textContent || 0),
        date: td[2] ? td[2].textContent.trim() : '',
        url: original ? original.getAttribute('href') : (td[3] ? td[3].textContent.trim() : ''),
        label: td[4] ? td[4].textContent.trim() : '',
    };
})"""


class NotLoggedIn(Exception):
    """edu.nl sent us to SURFconext to log in."""


class EdunlError(Exception):
    """edu.nl refused, with its own message."""


def on_manage(ctx: BrowserContext, url: str = MANAGE_URL) -> Page:
    """Open url (one of /manage/'s pages); raises NotLoggedIn when edu.nl wants a login first."""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(url, wait_until="load", timeout=30_000)
    deadline = time.monotonic() + SETTLE_S
    while time.monotonic() < deadline:
        try:
            if urlparse(page.url).hostname != HOST:
                raise NotLoggedIn(url)
            if page.locator('a[href="/logout"]').count():
                return page
        except PlaywrightError:
            pass  # navigating; look again
        page.wait_for_timeout(250)
    raise NotLoggedIn(url)


def logged_in(ctx: BrowserContext) -> bool:
    try:
        on_manage(ctx)
        return True
    except NotLoggedIn:
        return False


def shorten(ctx: BrowserContext, long_url: str) -> tuple[str, Page]:
    """Send long_url through the "Shorten a link" form; returns the short link and its page."""
    page = on_manage(ctx)
    page.fill("#short_url_longUrl", long_url)
    page.locator('form[name="short_url"] button[type="submit"]').click()
    deadline = time.monotonic() + SETTLE_S
    while time.monotonic() < deadline:
        try:
            if re.search(r"/manage/url/[^/]+/show$", urlparse(page.url).path):
                link = page.locator("a.cpy[data-clipboard-text]").first
                if link.count():
                    return link.get_attribute("data-clipboard-text"), page
            error = page.locator(".form-error-message").first
            if error.count():
                raise EdunlError(error.inner_text().strip())
        except PlaywrightError:
            pass  # still on its way
        page.wait_for_timeout(250)
    raise EdunlError(f"edu.nl didn't show a new link (the page is at {page.url}).")


def set_label(page: Page, label: str) -> None:
    """Give the link on its "created" page a label; only you see it, in your overview."""
    page.fill("#labelfield", label)
    page.locator('form[action$="/edit"] button[type="submit"]').click()
    deadline = time.monotonic() + SETTLE_S
    while time.monotonic() < deadline:
        try:
            if urlparse(page.url).path == "/manage/" and page.locator(".alert-success").count():
                return
        except PlaywrightError:
            pass
        page.wait_for_timeout(250)
    raise EdunlError("edu.nl didn't confirm the label.")


def links(ctx: BrowserContext, page_no: int = 1, search: str | None = None) -> tuple[list[dict], bool]:
    """One page of your links (newest first), and whether the overview has more pages."""
    query = f"?{urlencode({'filterValue': search, 'filterField': ''})}" if search else ""
    page = on_manage(ctx, f"{BASE_URL}/manage/page/{page_no}{query}")
    more = page.locator(f'.navigation a[href*="/manage/page/{page_no + 1}"]').count() > 0
    return page.evaluate(LINKS), more
