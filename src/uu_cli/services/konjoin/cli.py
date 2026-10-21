"""`uu konjoin <command>`."""

from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from uu_cli import auth, browser, paths
from uu_cli.services.konjoin.api import BASE_URL
from uu_cli.services.konjoin.commands import cmd_export, cmd_login, cmd_project, cmd_projects

COMMANDS = {
    "login": cmd_login,
    "projects": cmd_projects,
    "project": cmd_project,
    "export": cmd_export,
}


def main(argv: list[str] | None = None, prog: str | None = None) -> None:
    paths.ensure_state_dirs()

    def add_global_args(parser, suppress=False):
        # Subparsers use SUPPRESS so they don't overwrite values given before the subcommand
        d = (lambda v: argparse.SUPPRESS) if suppress else (lambda v: v)
        parser.add_argument("--session-dir", default=d(str(paths.SESSION_DIR)),
                            help="Browser profile, shared with the other services (one UU login)")
        auth.add_login_args(parser, d)

    p = argparse.ArgumentParser(
        prog=prog, description="Konjoin (uu.konjoin.nl): UU's research and thesis projects")
    add_global_args(p)
    common = argparse.ArgumentParser(add_help=False)
    add_global_args(common, suppress=True)

    sub = p.add_subparsers(dest="cmd", required=True)
    def cmd(*a, **kw):
        return sub.add_parser(*a, parents=[common], **kw)

    cmd("login", help="Log in through UU (and keep the session)")
    prj = cmd("projects", help="List projects; public ones need no login")
    prj.add_argument("-s", "--search", help="Search term, as in the site's search box")
    prj.add_argument("--page", type=int, default=1)
    prj.add_argument("--all", action="store_true", help="Every page instead of one")
    prj.add_argument("--json", action="store_true", help="Print the raw project data")
    one = cmd("project", help="Show one project (needs a login)")
    one.add_argument("slug", help="The project's slug, as listed by `projects` (e.g. 3208-some-title)")
    one.add_argument("--json", action="store_true", help="Print the raw project data")
    exp = cmd("export", help="Save every project to a JSON file")
    exp.add_argument("-o", "--output", required=True, help="JSON file to write")
    exp.add_argument("-s", "--search", help="Only projects matching this search term")

    args = p.parse_args(argv)

    with sync_playwright() as pw:
        ctx = browser.launch(pw, args.session_dir)
        browser.own_files_only(ctx, urlparse(BASE_URL).hostname)
        try:
            sys.exit(COMMANDS[args.cmd](ctx, args))
        finally:
            browser.save_session(ctx, args.session_dir)
