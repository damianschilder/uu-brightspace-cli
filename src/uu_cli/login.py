"""Log in through UU's Solis-id page: the NetIQ form, then the one-time code."""

from __future__ import annotations

import sys
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext

from uu_cli import paths
from uu_cli.auth.totp_secret import totp


def do_login(ctx: BrowserContext, start_url: str, solisid: str, password: str,
             totp_secret: str, name: str = "Brightspace") -> None:
    """Open start_url, which redirects to the Solis-id form, and log in until back on its host."""
    if not solisid:
        print("ERROR: --solisid or BRIGHTSPACE_SOLISID required for login",
              file=sys.stderr)
        sys.exit(1)

    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    print(f"[AUTH] Navigating to {name}...", file=sys.stderr)
    page.goto(start_url, wait_until="load", timeout=30_000)
    page.wait_for_selector("#Ecom_User_ID", timeout=20_000)
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
        page.screenshot(path=str(paths.SESSION_DIR / "debug_otp_missing.png"))
        with open(str(paths.SESSION_DIR / "debug_otp_missing.html"), "w") as f:
            f.write(page.content())
        body_text = page.inner_text("body")[:300]
        print(f"[AUTH] OTP not found. Body: {body_text}", file=sys.stderr)
        raise RuntimeError(f"OTP field not found. URL={page.url}")

    print(f"[AUTH] OTP field found: {otp_sel}", file=sys.stderr)

    code = totp(totp_secret)
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

    if urlparse(page.url).hostname != urlparse(start_url).hostname:
        page.screenshot(path=str(paths.SESSION_DIR / f"debug_not_{name.lower()}.png"))
        with open(str(paths.SESSION_DIR / f"debug_not_{name.lower()}.html"), "w") as f:
            f.write(page.content())
        body_text = page.inner_text("body")[:300]
        raise RuntimeError(f"Post-OTP URL is not {name}: {page.url}\nBody: {body_text}")

    print(f"[AUTH] ✓ Logged in: {page.url}", file=sys.stderr)
    page.wait_for_timeout(2000)
