"""The prompt route: you type the code from your own authenticator app (Authy, Google Authenticator, ...).

The secret never leaves your phone; a login needs you at the terminal.
"""

from __future__ import annotations

import sys


class PromptCode:
    name = "prompt"

    def code(self) -> str:
        while True:
            code = input("Code from your authenticator app: ").strip().replace(" ", "")
            if len(code) == 6 and code.isdigit():
                return code
            print("That is not a 6-digit code; try again.", file=sys.stderr)
