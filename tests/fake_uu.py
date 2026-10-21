"""An offline stand-in for UU's Solis-id login and Brightspace, served through Playwright routing.

It models what the CLI relies on, not the real services: a NetIQ-style form with a one-time-code
step, a SAML-style hop back that sets a session cookie, a D2L token in localStorage, and the API
endpoints the commands call. Every other request is aborted and redirects happen in the page,
so nothing leaves the machine.
"""

from __future__ import annotations

import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pyotp

BRIGHTSPACE = "https://uu.brightspace.com"
IDP = "https://login.uu.nl"
SOLISID = "1234567"
PASSWORD = "correct horse"
TOTP_SECRET = "JBSWY3DPEHPK3PXP"
ORG_UNIT = "4242"
COURSE = "/content/enforced/4242-INFOMAI"
PDF = b"%PDF-1.4\n% fake course file\n"

# Lets the CLI's fetch() from about:blank reach the API, as a cached-token command does.
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization, Accept",
}

LOGIN_FORM = """
<form method="post" action="/nidp/app/login?sid=0">
  <input id="Ecom_User_ID" name="Ecom_User_ID" type="text">
  <input id="Ecom_Password" name="Ecom_Password" type="password">
  <button id="loginButton2" type="submit">Login</button>
</form>"""

OTP_FORM = """
<form method="post" action="/nidp/app/login?sid=1">
  <label for="nffc">Code from your authenticator app</label>
  <input id="nffc" name="nffc" type="text" autocomplete="one-time-code" maxlength="6">
  <button id="loginButton2" type="submit">Verify</button>
</form>"""

HOME = """<h1>My Home</h1>
<script>localStorage.setItem('D2L.Fetch.Tokens',
  JSON.stringify({"*:*:*": {"access_token": "TOKEN", "expires_at": 0}}));</script>"""

READING = """<h1>Reading</h1>
<p>See the <a href="handout.pdf">handout</a> and <a href="https://example.org/x.pdf">an outside link</a>.</p>"""

API = {
    "/d2l/api/lp/1.43/enrollments/myenrollments/": {"Items": [
        {"OrgUnit": {"Id": 4242, "Code": "INFOMAI", "Name": "Fake Course", "Type": {"Id": 3}}},
        {"OrgUnit": {"Id": 99, "Code": "GRP-1", "Name": "Project group", "Type": {"Id": 4}}},
    ]},
    f"/d2l/api/le/1.57/{ORG_UNIT}/content/toc": {"Modules": [{
        "ModuleId": 1, "Title": "Week 1", "Description": {"Text": "", "Html": ""}, "Modules": [],
        "Topics": [
            {"TopicId": 11, "Title": "Slides", "TypeIdentifier": "File", "Url": f"{COURSE}/slides.pdf"},
            {"TopicId": 12, "Title": "Reading", "TypeIdentifier": "File", "Url": f"{COURSE}/reading.html"},
            {"TopicId": 13, "Title": "Course site", "Type": "ExternalLink", "Url": "https://example.org/course"},
            {"TopicId": 14, "Title": "Welcome", "TypeIdentifier": "Link",
             "Url": f"/d2l/le/content/{ORG_UNIT}/viewContent/14/View"},
        ],
    }]},
    f"/d2l/api/le/1.57/{ORG_UNIT}/content/1/topics/14/": {"Body": "<p>Welcome to the course.</p>"},
    f"/d2l/api/le/1.57/{ORG_UNIT}/dropbox/folders/": [{
        "Id": 7, "Name": "Essay 1", "CategoryId": None,
        "StartDate": "2026-10-01T00:00:00.000Z", "DueDate": "2026-11-01T22:59:00.000Z",
        "CustomInstructions": {"Text": "Read the brief.",
                               "Html": f'<p><a href="{COURSE}/brief.pdf">Brief</a></p>'},
    }],
    f"/d2l/api/le/1.57/{ORG_UNIT}/news/": [{
        "Title": "Room change", "IsPublished": True, "CreatedDate": "2026-10-15T09:00:00.000Z",
        "Body": {"Text": "Lecture moves to Ruppert 040.", "Html": ""}, "Attachments": [],
    }],
    f"/d2l/api/le/1.57/{ORG_UNIT}/grades/values/myGradeValues/": [
        {"DisplayName": "Essay 1", "WeightedNumerator": 7.5, "WeightedDenominator": 10},
    ],
}


def make_jwt(exp: float) -> str:
    """An unsigned JWT with an 'exp' claim, enough for the CLI's expiry check."""
    def part(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{part({'alg': 'none'})}.{part({'exp': int(exp), 'sub': SOLISID})}.sig"


class FakeUU:
    def __init__(self) -> None:
        self.token = make_jwt(time.time() + 3600)
        self.codes: list[str] = []  # one-time codes the login form received
        self.logins = 0             # completed logins (hops back to Brightspace)

    def install(self, ctx) -> None:
        ctx.route("**/*", self._handle)

    # ── dispatch ──────────────────────────────────────────────────────────────
    def _handle(self, route) -> None:
        req = route.request
        url = urlparse(req.url)
        origin = f"{url.scheme}://{url.netloc}"
        if origin == IDP:
            self._idp(route, req, url)
        elif origin == BRIGHTSPACE:
            self._brightspace(route, req, url)
        else:
            route.abort()

    # ── UU's login (the identity provider) ────────────────────────────────────
    def _idp(self, route, req, url) -> None:
        if url.path != "/nidp/app/login":
            return route.fulfill(status=404, body="not found")
        if req.method == "GET":
            if "IDP_SESSION=" in _cookies(req):  # single sign-on: still logged in at UU
                return _redirect(route, f"{BRIGHTSPACE}/d2l/lp/auth/saml/acs")
            return _html(route, LOGIN_FORM)
        form = {k: v[0] for k, v in parse_qs(req.post_data or "").items()}
        if parse_qs(url.query).get("sid") == ["0"]:
            if form.get("Ecom_User_ID") == SOLISID and form.get("Ecom_Password") == PASSWORD:
                return _html(route, OTP_FORM)
            return _html(route, "<p>Wrong Solis-id or password.</p>" + LOGIN_FORM)
        code = form.get("nffc", "")
        self.codes.append(code)
        if pyotp.TOTP(TOTP_SECRET).verify(code, valid_window=1):
            return _redirect(route, f"{BRIGHTSPACE}/d2l/lp/auth/saml/acs",
                             cookie="IDP_SESSION=1; Path=/")
        return _html(route, "<p>Wrong code.</p>" + OTP_FORM)

    # ── Brightspace ───────────────────────────────────────────────────────────
    def _brightspace(self, route, req, url) -> None:
        path = url.path
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        if path.startswith("/d2l/api/"):
            return self._api(route, req, path)
        if path == "/d2l/lp/auth/saml/acs":
            self.logins += 1
            return _redirect(route, f"{BRIGHTSPACE}/d2l/home", cookie="d2lSessionVal=s3ss; Path=/")
        if "d2lSessionVal=" not in _cookies(req):
            return _redirect(route, f"{IDP}/nidp/app/login")
        if path in ("/", "/d2l/home"):
            return _html(route, HOME.replace("TOKEN", self.token))
        name = path.rsplit("/", 1)[-1]
        if path.startswith(COURSE + "/") and name.endswith(".pdf"):
            return route.fulfill(status=200, body=PDF, headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": f'attachment; filename="{name}"',
            })
        if path == f"{COURSE}/reading.html":
            return _html(route, READING)
        route.fulfill(status=404, body="not found")

    def _api(self, route, req, path) -> None:
        if req.all_headers().get("authorization") != f"Bearer {self.token}":
            return _json(route, {"Errors": [{"Message": "Unauthorized"}]}, status=401)
        if path not in API:
            return _json(route, {"Errors": [{"Message": "Not found"}]}, status=404)
        _json(route, API[path])


def _cookies(req) -> str:
    return req.all_headers().get("cookie", "")


def _html(route, body: str) -> None:
    # Pad past the CLI's "tiny page that mentions login" check, which real pages never trip.
    page = f"<!doctype html><html><body>{body}<!-- {'.' * 600} --></body></html>"
    route.fulfill(status=200, body=page, headers={"Content-Type": "text/html; charset=utf-8"})


def _json(route, data, status: int = 200) -> None:
    route.fulfill(status=status, body=json.dumps(data),
                  headers={"Content-Type": "application/json", **CORS})


def _redirect(route, location: str, cookie: str | None = None) -> None:
    # A client-side hop, never a 302: Playwright routes only the first URL of a server redirect,
    # so the follow-up request would bypass this fake and go out to the real host.
    headers = {"Content-Type": "text/html; charset=utf-8"}
    if cookie:
        headers["Set-Cookie"] = cookie
    body = f"<!doctype html><html><head><script>location.replace({json.dumps(location)})</script></head></html>"
    route.fulfill(status=200, headers=headers, body=body)
