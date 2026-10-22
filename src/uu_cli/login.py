"""Log in through UU's Solis-id page: the NetIQ form, then the one-time code.

Services reach that page their own way: Brightspace redirects straight to it, Konjoin goes
through SURFconext, which may first ask which institution to use. One UU login also covers
the next service while UU's session lasts (single sign-on).
"""

from __future__ import annotations

import re
import sys
import time
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Error as PlaywrightError, Page

from uu_cli import paths
from uu_cli.auth import OtpRoute

# How UU appears in SURFconext's institution picker (English or Dutch); not "UMC Utrecht".
UU_IN_SURFCONEXT = re.compile(r"Utrecht University|Universiteit Utrecht")


def single_sign_on(ctx: BrowserContext, start_url: str) -> bool:
    """Open start_url; True when an existing UU session logs in without showing the form."""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(start_url, wait_until="load", timeout=30_000)
    return not _reach_login_form(page, urlparse(start_url).hostname)


def do_login(ctx: BrowserContext, start_url: str, solisid: str, password: str,
             otp: OtpRoute, name: str = "Brightspace") -> None:
    """Open start_url, which redirects to the Solis-id form, and log in until back on its host.

    The one-time code comes from otp (see uu_cli.auth), asked for once the code form is up.
    """
    if not solisid:
        print("ERROR: --solisid or BRIGHTSPACE_SOLISID required for login",
              file=sys.stderr)
        sys.exit(1)

    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    print(f"[AUTH] Navigating to {name}...", file=sys.stderr)
    page.goto(start_url, wait_until="load", timeout=30_000)
    if not _reach_login_form(page, urlparse(start_url).hostname):
        print(f"[AUTH] ✓ Already logged in at UU: {page.url}", file=sys.stderr)
        return
    print(f"[AUTH] At NISP form: {page.url}", file=sys.stderr)

    print("[AUTH] Filling credentials...", file=sys.stderr)
    page.fill("#Ecom_User_ID", solisid)
    page.fill("#Ecom_Password", password)
    page.click("#loginButton2")

    print("[AUTH] Waiting for OTP form...", file=sys.stderr)
    page.wait_for_timeout(3000)
    print(f"[AUTH] URL: {page.url}", file=sys.stderr)

    otp_sel = page.evaluate(
        "() => {"
        "  const el = document.querySelector("
        "    'input[autocomplete=\"one-time-code\"],"
        "    input[autocomplete=\"one-time-password\"],"
        "    input[autocomplete=\"otp\"],"
        "    input[maxlength=\"6\"],"
        "    input[type=\"text\"]'"
        "  );"
        "  if (el && el.id) return '#' + el.id;"
        "  if (el && el.name) return 'input[name=\"' + el.name + '\"]';"
        "  return null;"
        "}"
    )

    if not otp_sel:
        _dump(page, "debug_otp_missing")
        body_text = page.inner_text("body")[:300]
        print(f"[AUTH] OTP not found. Body: {body_text}", file=sys.stderr)
        raise RuntimeError(f"OTP field not found. URL={page.url}")

    print(f"[AUTH] OTP field found: {otp_sel}", file=sys.stderr)

    code = otp.code()
    page.fill(otp_sel, code)

    button_selectors = ["#loginButton2", "button[type='submit']",
                        "input[type='submit']", "button"]
    btn_sel = None
    for sel in button_selectors:
        if page.locator(sel).count() > 0:
            btn_sel = sel
            break

    if btn_sel:
        page.click(btn_sel)
    else:
        page.keyboard.press("Enter")

    print(f"[AUTH] Waiting for {name}...", file=sys.stderr)
    page.wait_for_timeout(5000)
    print(f"[AUTH] URL: {page.url}", file=sys.stderr)

    host = urlparse(page.url).hostname or ""
    if host != urlparse(start_url).hostname:
        _dump(page, f"debug_not_{name.lower()}")
        body_text = page.inner_text("body")[:300]
        hint = ("\nSURFconext may be asking for your consent to share your details with "
                f"{name}; log in once in a normal browser to give it."
                if host.endswith("surfconext.nl") else "")
        raise RuntimeError(f"Post-OTP URL is not {name}: {page.url}\nBody: {body_text}{hint}")

    print(f"[AUTH] ✓ Logged in: {page.url}", file=sys.stderr)
    page.wait_for_timeout(2000)


def _reach_login_form(page: Page, target_host: str | None, timeout_s: float = 30) -> bool:
    """Follow a service's redirects to the Solis-id form; False when they end on target_host instead.

    Picks UU when SURFconext asks for an institution. Ending up (and staying) back on the
    service without a form means UU's session logged us in already.
    """
    deadline = time.monotonic() + timeout_s
    picked_on = None
    on_target_since = None
    while time.monotonic() < deadline:
        try:
            if page.locator("#Ecom_User_ID").count():
                return True
            host = urlparse(page.url).hostname or ""
            if host.endswith("surfconext.nl") and page.url != picked_on:
                uu = page.get_by_text(UU_IN_SURFCONEXT).first
                if uu.count():
                    print("[AUTH] SURFconext: choosing Utrecht University", file=sys.stderr)
                    picked_on = page.url
                    uu.click()
            if host == target_host:
                on_target_since = on_target_since or time.monotonic()
                if time.monotonic() - on_target_since > 2:
                    return False
            else:
                on_target_since = None
        except PlaywrightError:
            pass  # the page navigated mid-check; look again
        page.wait_for_timeout(250)
    _dump(page, "debug_login_form_missing")
    raise RuntimeError(f"UU login form not found. URL={page.url}")


def _dump(page: Page, name: str) -> None:
    """Save a screenshot and the HTML of a page that broke the login, for debugging."""
    page.screenshot(path=str(paths.SESSION_DIR / f"{name}.png"))
    with open(str(paths.SESSION_DIR / f"{name}.html"), "w") as f:
        f.write(page.content())
