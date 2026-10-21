"""Generate the 6-digit login code from the TOTP secret behind your authenticator entry."""

from __future__ import annotations

import pyotp


def totp(secret: str) -> str:
    return pyotp.TOTP(secret).now()
