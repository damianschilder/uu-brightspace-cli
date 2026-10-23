"""`uu gitlab <command>`."""

from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

from uu_cli import auth, browser, paths
from uu_cli.services.gitlab.api import HOST, GitLabError, NotLoggedIn
from uu_cli.services.gitlab.commands import cmd_add_key, cmd_create, cmd_login, cmd_projects

COMMANDS = {
    "login": cmd_login,
    "projects": cmd_projects,
    "create": cmd_create,
    "add-key": cmd_add_key,
}


def main(argv: list[str] | None = None, prog: str | None = None) -> None:
    paths.ensure_state_dirs()

    def add_global_args(parser, suppress=False):
        # Subparsers use SUPPRESS so they don't overwrite values given before the subcommand
        d = (lambda v: argparse.SUPPRESS) if suppress else (lambda v: v)
        parser.add_argument("--session-dir", default=d(str(paths.SESSION_DIR)),
                            help="Browser profile, shared with the other services")
        auth.add_login_args(parser, d)

    p = argparse.ArgumentParser(
        prog=prog, description=f"GitLab ({HOST}): the Faculty of Science's GitLab",
        epilog="GitLab asks no one-time code: every --auth but browser fills in its Solis-ID "
               "sign-in with your Solis-id and password.")
    add_global_args(p)
    common = argparse.ArgumentParser(add_help=False)
    add_global_args(common, suppress=True)

    sub = p.add_subparsers(dest="cmd", required=True)
    def cmd(*a, **kw):
        return sub.add_parser(*a, parents=[common], **kw)

    cmd("login", help="Log in with your Solis-id (and keep the session)")
    cmd("projects", help="List the projects you own or are a member of")
    new = cmd("create", help="Create an empty project, for an existing repo's first push")
    new.add_argument("name", help="The project's name; its address follows from it")
    new.add_argument("--description")
    new.add_argument("--visibility", choices=["private", "internal", "public"], default="private",
                     help="private (default): only you and members you add; internal: everyone "
                          f"who can log in to {HOST}; public: anyone")
    key = cmd("add-key", help="Add your public SSH key to your account, so git can push over SSH")
    key.add_argument("file", nargs="?", default="~/.ssh/id_ed25519.pub",
                     help="Your public key (default: ~/.ssh/id_ed25519.pub)")
    key.add_argument("--title", help="The key's name in GitLab (default: this computer's name)")

    args = p.parse_args(argv)

    with sync_playwright() as pw:
        ctx = browser.launch(pw, args.session_dir)
        browser.own_files_only(ctx, HOST)
        try:
            sys.exit(COMMANDS[args.cmd](ctx, args))
        except GitLabError as err:
            print(f"ERROR: {err}", file=sys.stderr)
            sys.exit(1)
        except NotLoggedIn:
            print("ERROR: GitLab ended the session; run `uu gitlab login` again.", file=sys.stderr)
            sys.exit(1)
        finally:
            browser.save_session(ctx, args.session_dir)
