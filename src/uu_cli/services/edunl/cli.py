"""`uu edunl <command>`."""

from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

from uu_cli import auth, browser, paths
from uu_cli.services.edunl.api import HOST
from uu_cli.services.edunl.commands import cmd_links, cmd_login, cmd_shorten

COMMANDS = {
    "login": cmd_login,
    "shorten": cmd_shorten,
    "links": cmd_links,
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
        prog=prog, description="edu.nl: SURF's URL shortener for education and research")
    add_global_args(p)
    common = argparse.ArgumentParser(add_help=False)
    add_global_args(common, suppress=True)

    sub = p.add_subparsers(dest="cmd", required=True)
    def cmd(*a, **kw):
        return sub.add_parser(*a, parents=[common], **kw)

    cmd("login", help="Log in through SURFconext and UU (and keep the session)")
    sh = cmd("shorten", help="Make a short edu.nl link; prints the link")
    sh.add_argument("url", help="The web address to shorten (http:// or https://)")
    sh.add_argument("--label", help="A label for the link, which only you see in your overview")
    li = cmd("links", help="Your links, newest first")
    li.add_argument("-s", "--search", help="Search term, as in the overview's search box")
    li.add_argument("--page", type=int, default=1)
    li.add_argument("--json", action="store_true", help="Print the links as JSON")

    args = p.parse_args(argv)

    with sync_playwright() as pw:
        ctx = browser.launch(pw, args.session_dir)
        browser.own_files_only(ctx, HOST)
        try:
            sys.exit(COMMANDS[args.cmd](ctx, args))
        finally:
            browser.save_session(ctx, args.session_dir)
