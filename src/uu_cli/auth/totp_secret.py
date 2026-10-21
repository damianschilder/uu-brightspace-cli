"""The totp-secret route: generate the 6-digit code from the secret behind your authenticator entry.

Runs unattended (cron, Docker), at the price of keeping the secret on this machine.
"""

from __future__ import annotations

import pyotp


def totp(secret: str) -> str:
    return pyotp.TOTP(secret).now()


class TotpSecret:
    name = "totp-secret"

    def __init__(self, secret: str) -> None:
        self.secret = secret

    def code(self) -> str:
        return totp(self.secret)
