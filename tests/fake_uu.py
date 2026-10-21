"""An offline stand-in for UU's Solis-id login, Brightspace and Konjoin, served through Playwright routing.

It models what the CLI relies on, not the real services: a NetIQ-style form with a one-time-code
step and a single-sign-on session, SAML-style hops back that set a session cookie, a D2L token
in localStorage, SURFconext's institution picker in front of Konjoin, and the API endpoints the
commands call. Every other request is aborted and redirects happen in the page, so nothing
leaves the machine.
"""

from __future__ import annotations

import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pyotp

BRIGHTSPACE = "https://uu.brightspace.com"
KONJOIN = "https://uu.konjoin.nl"
SURFCONEXT = "https://engine.surfconext.nl"
IDP = "https://login.uu.nl"
SOLISID = "1234567"
PASSWORD = "correct horse"
TOTP_SECRET = "JBSWY3DPEHPK3PXP"
ORG_UNIT = "4242"
COURSE = "/content/enforced/4242-INFOMAI"
PDF = b"%PDF-1.4\n% fake course file\n"

# Where UU's login sends you back to, per service (the "sp" parameter).
ACS = {
    "brightspace": f"{BRIGHTSPACE}/d2l/lp/auth/saml/acs",
    "konjoin": f"{KONJOIN}/saml2/acs",
}

# Lets the CLI's fetch() from about:blank reach the API, as a cached-token command does.
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization, Accept",
}

LOGIN_FORM = """
<form method="post" action="/nidp/app/login?sid=0&sp={sp}">
  <input id="Ecom_User_ID" name="Ecom_User_ID" type="text">
  <input id="Ecom_Password" name="Ecom_Password" type="password">
  <button id="loginButton2" type="submit">Login</button>
</form>"""

OTP_FORM = """
<form method="post" action="/nidp/app/login?sid=1&sp={sp}">
  <label for="nffc">Code from your authenticator app</label>
  <input id="nffc" name="nffc" type="text" autocomplete="one-time-code" maxlength="6">
  <button id="loginButton2" type="submit">Verify</button>
</form>"""

WAYF = f"""<h1>Select an institution to log in</h1>
<ul>
  <li><a href="{SURFCONEXT}/wayf/umc">UMC Utrecht</a></li>
  <li><a href="{IDP}/nidp/app/login?sp=konjoin">Utrecht University</a></li>
</ul>"""

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

# Konjoin's project list, in the shape /api/project returns (made-up projects).
PROJECTS = [
    {"id": 3208, "slug": "3208-neurogenetics-elective", "label": "Neurogenetics elective",
     "status": {"id": 1, "label": "open"}, "public": True,
     "institute": {"label": "Department of Medicine"},
     "description": "<p>Why does one person develop a neurological disorder &amp; another not?</p>"
                    "<ul><li>Clinical genetics</li><li>Eight weeks</li></ul>",
     "leader": {"full_name": "Anoniem", "email": "leader@example.org", "organization_uid": "1000001"},
     "collaborators": [{"full_name": "Dr. A. Example", "email": "a.example@example.org",
                        "organization_uid": "1000002"}],
     "studies": [{"label": "Medicine"}], "types": [{"label": "Internship"}],
     "created_at": "2026-10-20T08:06:03.000000Z", "close_at": None},
    {"id": 3100, "slug": "3100-trade-routes-in-still-lifes", "label": "Trade routes in Dutch still lifes",
     "status": {"id": 1, "label": "open"}, "public": True,
     "institute": {"label": "Department of Information and Computing Sciences"},
     "description": "<p>Object recognition on 17th-century paintings.</p>",
     "leader": {"full_name": "Dr. B. Example"}, "collaborators": [], "studies": [], "types": [],
     "created_at": "2026-09-01T10:00:00.000000Z", "close_at": "2026-12-01T00:00:00.000000Z"},
    {"id": 2990, "slug": "2990-soil-microbes-and-drought", "label": "Soil microbes and drought",
     "status": {"id": 2, "label": "closed"}, "public": True,
     "institute": {"label": "Faculty of Geosciences"},
     "description": "<p>Field work in the Veluwe.</p>",
     "leader": {"full_name": "Prof. C. Example"}, "collaborators": [], "studies": [], "types": [],
     "created_at": "2026-05-01T10:00:00.000000Z", "close_at": None},
]
PER_PAGE = 2
# What Konjoin's real pages wait for before they count as loaded (seen 22-10-2026).
THIRD_PARTY = """<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Lato">
<script src="https://cdn.polyfill.io/v2/polyfill.min.js"></script>"""


def make_jwt(exp: float) -> str:
    """An unsigned JWT with an 'exp' claim, enough for the CLI's expiry check."""
    def part(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{part({'alg': 'none'})}.{part({'exp': int(exp), 'sub': SOLISID})}.sig"


class FakeUU:
    def __init__(self) -> None:
        self.token = make_jwt(time.time() + 3600)
        self.codes: list[str] = []  # one-time codes the login form received
        self.logins = 0             # completed logins at Brightspace
        self.konjoin_logins = 0     # completed logins at Konjoin
        self.wayf_choices = 0       # times SURFconext's institution picker was answered
        self.elsewhere: list[str] = []  # requests for hosts this fake doesn't serve (aborted)

    def install(self, ctx) -> None:
        ctx.route("**/*", self._handle)

    # ── dispatch ──────────────────────────────────────────────────────────────
    def _handle(self, route) -> None:
        req = route.request
        url = urlparse(req.url)
        origin = f"{url.scheme}://{url.netloc}"
        handler = {
            IDP: self._idp,
            BRIGHTSPACE: self._brightspace,
            KONJOIN: self._konjoin,
            SURFCONEXT: self._surfconext,
        }.get(origin)
        if handler:
            handler(route, req, url)
        else:
            self.elsewhere.append(req.url)
            route.abort()

    # ── UU's login (the identity provider) ────────────────────────────────────
    def _idp(self, route, req, url) -> None:
        if url.path != "/nidp/app/login":
            return route.fulfill(status=404, body="not found")
        query = parse_qs(url.query)
        sp = query.get("sp", ["brightspace"])[0]
        if req.method == "GET":
            if sp == "konjoin":  # only SURFconext's picker links here
                self.wayf_choices += 1
            if "IDP_SESSION=" in _cookies(req):  # single sign-on: still logged in at UU
                return _redirect(route, ACS[sp])
            return _html(route, LOGIN_FORM.format(sp=sp))
        form = {k: v[0] for k, v in parse_qs(req.post_data or "").items()}
        if query.get("sid") == ["0"]:
            if form.get("Ecom_User_ID") == SOLISID and form.get("Ecom_Password") == PASSWORD:
                return _html(route, OTP_FORM.format(sp=sp))
            return _html(route, "<p>Wrong Solis-id or password.</p>" + LOGIN_FORM.format(sp=sp))
        code = form.get("nffc", "")
        self.codes.append(code)
        if pyotp.TOTP(TOTP_SECRET).verify(code, valid_window=1):
            return _redirect(route, ACS[sp], cookie="IDP_SESSION=1; Path=/")
        return _html(route, "<p>Wrong code.</p>" + OTP_FORM.format(sp=sp))

    # ── SURFconext, in front of Konjoin ───────────────────────────────────────
    def _surfconext(self, route, req, url) -> None:
        if url.path.startswith("/authentication/idp/single-sign-on"):
            return _html(route, WAYF)
        route.fulfill(status=404, body="not found")

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
            return _redirect(route, f"{IDP}/nidp/app/login?sp=brightspace")
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

    # ── Konjoin ───────────────────────────────────────────────────────────────
    def _konjoin(self, route, req, url) -> None:
        path, query = url.path, parse_qs(url.query)
        logged_in = "laravel_session=" in _cookies(req)
        if path == "/saml2/login":
            return _redirect(route, f"{SURFCONEXT}/authentication/idp/single-sign-on?SAMLRequest=x")
        if path == "/saml2/acs":
            self.konjoin_logins += 1
            return _redirect(route, f"{KONJOIN}/", cookie="laravel_session=k0nj; Path=/")
        if path == "/":
            user = ('<meta name="user-id" content="42"><meta name="user-name" content="Test Student">'
                    if logged_in else "")
            return _html(route, f"<head>{user}{THIRD_PARTY}</head><h1>KonJoin</h1>")
        if path == "/api/project":
            term = query.get("query", [""])[0].lower()
            found = [p for p in PROJECTS if term in p["label"].lower()]
            page = int(query.get("page", ["1"])[0])
            last = max(1, -(-len(found) // PER_PAGE))
            return _json(route, {
                "current_page": page, "last_page": last, "per_page": PER_PAGE, "total": len(found),
                "data": found[(page - 1) * PER_PAGE:page * PER_PAGE],
            })
        if path.startswith("/api/project/"):
            if not logged_in:
                return _json(route, {"message": "Unauthenticated."}, status=401)
            slug = path.rsplit("/", 1)[-1]
            project = next((p for p in PROJECTS if p["slug"] == slug), None)
            if project is None:
                return _json(route, {"message": "Not found."}, status=404)
            return _json(route, project)
        route.fulfill(status=404, body="not found")


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
