"""How a login answers UU's one-time-code step.

Each route is a module in this package with a class that has a `name` and a `code()` method,
registered in ROUTES:

  totp-secret  generate the code from your TOTP secret (unattended: cron, Docker)
  prompt       ask you for the code from your own authenticator app

`--auth auto` (the default) uses the secret when one is set and asks you otherwise.
"""

from __future__ import annotations

import getpass
import os
import sys
from typing import Protocol

from uu_cli.auth.credentials import have_creds
from uu_cli.auth.prompt import PromptCode
from uu_cli.auth.totp_secret import TotpSecret


class OtpRoute(Protocol):
    name: str

    def code(self) -> str: ...


ROUTES = {route.name: route for route in (TotpSecret, PromptCode)}

CANNOT_LOGIN = ("a login needs --password and --totp (or save-creds), "
                "or a terminal to type the code from your authenticator app")


def add_login_args(parser, d=lambda v: v) -> None:
    """The login options every service shares. d wraps defaults (argparse.SUPPRESS on subcommands)."""
    parser.add_argument("--solisid",  default=d(os.environ.get("BRIGHTSPACE_SOLISID")))
    parser.add_argument("--password", default=d(os.environ.get("BRIGHTSPACE_PASSWORD", "")),
                        help="Visible in `ps` and shell history; prefer save-creds")
    parser.add_argument("--totp",     default=d(os.environ.get("BRIGHTSPACE_TOTP_SECRET", "")),
                        help="TOTP secret key (base32), not a 6-digit code; prefer save-creds")
    parser.add_argument("--auth", choices=["auto", *ROUTES],
                        default=d(os.environ.get("BRIGHTSPACE_AUTH", "auto")),
                        help="How to answer the one-time-code step: totp-secret generates it, "
                             "prompt asks for the code from your authenticator app; "
                             "auto (default) uses the secret when one is set")


def interactive() -> bool:
    """Whether someone is at the terminal to type a code."""
    return sys.stdin.isatty()


def ready_to_login(args) -> bool:
    """Fill in what a login needs and settle args.auth; True when a login can go ahead.

    Missing details come from the encrypted credentials file first. Without a TOTP secret the
    prompt route asks you for the code, and for a missing Solis-id or password too; that needs a
    terminal, so unattended runs still need the secret.
    """
    have_creds(args)
    if args.auth == "auto":
        args.auth = "totp-secret" if args.totp or not interactive() else "prompt"
    if args.auth == "totp-secret":
        return bool(args.password and args.totp)
    if not interactive():
        print("ERROR: --auth prompt needs a terminal to type the code in.", file=sys.stderr)
        return False
    args.solisid = args.solisid or input("Solis-id: ").strip()
    args.password = args.password or getpass.getpass("Password: ")
    return bool(args.solisid and args.password)


def otp_route(args) -> OtpRoute:
    if args.auth == "prompt" or (args.auth == "auto" and not args.totp):
        return PromptCode()
    return TotpSecret(args.totp)
