"""GitLab's REST API (/api/v4), called from a GitLab page the way GitLab's own pages call it.

The session cookie goes along, and a request that changes something carries the page's CSRF
token: GitLab accepts a session cookie for anything but GET and HEAD only with a valid
X-CSRF-Token (Gitlab::Auth::AuthFinders#verified_request?). The token belongs to the session,
so a page loaded before a login carries a stale one; current_user loads a fresh page.
"""

from __future__ import annotations

import json
import os
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page

BASE_URL = os.environ.get("UU_GITLAB_URL", "https://git.science.uu.nl").rstrip("/")
HOST = urlparse(BASE_URL).hostname
SIGN_IN_URL = f"{BASE_URL}/users/sign_in"


class NotLoggedIn(Exception):
    """GitLab wants a login for this request."""


class GitLabError(Exception):
    """GitLab refused a request; the message is GitLab's own."""


def current_user(ctx: BrowserContext) -> dict | None:
    """The logged-in user (/api/v4/user), or None for a guest."""
    _page(ctx).goto(BASE_URL + "/", wait_until="load", timeout=30_000)
    try:
        return call(ctx, "GET", "/user")
    except NotLoggedIn:
        return None


def call(ctx: BrowserContext, method: str, path: str, data: dict | None = None):
    """Send an /api/v4 request and return its JSON. Raises NotLoggedIn or GitLabError."""
    page = _page(ctx)
    if urlparse(page.url).hostname != HOST:
        page.goto(BASE_URL + "/", wait_until="load", timeout=30_000)
    result = page.evaluate("""async ([method, url, data]) => {
        const headers = {"Accept": "application/json"};
        const token = document.querySelector('meta[name="csrf-token"]')?.content;
        if (token) headers["X-CSRF-Token"] = token;
        if (data !== null) headers["Content-Type"] = "application/json";
        const r = await fetch(url, {method, headers, credentials: "same-origin",
                                    body: data === null ? undefined : JSON.stringify(data)});
        return {status: r.status, body: await r.text()};
    }""", [method, f"{BASE_URL}/api/v4{path}", data])
    if result["status"] == 401:
        raise NotLoggedIn(path)
    try:
        body = json.loads(result["body"]) if result["body"] else None
    except ValueError:
        body = result["body"][:200]
    if not 200 <= result["status"] < 300:
        raise GitLabError(f"GitLab {method} {path}: HTTP {result['status']}: {_message(body)}")
    return body


def _message(body) -> str:
    """GitLab's error, flattened: {"message": {"path": ["has already been taken"]}} -> path has already been taken."""
    msg = (body.get("message") or body.get("error")) if isinstance(body, dict) else body
    if isinstance(msg, dict):
        return "; ".join(f"{field} {', '.join(map(str, v)) if isinstance(v, list) else v}"
                         for field, v in msg.items())
    return str(msg or "")


def _page(ctx: BrowserContext) -> Page:
    return ctx.pages[0] if ctx.pages else ctx.new_page()
