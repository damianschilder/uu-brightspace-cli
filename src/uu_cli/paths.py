"""Where the CLI keeps its state: browser session, token, saved credentials and downloads."""

from __future__ import annotations

import os
from pathlib import Path

# A source checkout keeps its state next to the repo (../brightspace/), as brightspace-cli.py
# always did. An installed package has no checkout, so it falls back to the user data dir.
_CHECKOUT = Path(__file__).parents[2]
if (_CHECKOUT / "pyproject.toml").exists():
    STATE_PARENT = _CHECKOUT.parent
else:
    STATE_PARENT = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "uu-cli"

SESSION_DIR = Path(os.environ.get("BRIGHTSPACE_SESSION_DIR",
                         str(STATE_PARENT / "brightspace" / "session")))
TOKEN_FILE = Path(os.environ.get("BRIGHTSPACE_TOKEN_FILE",
                         str(STATE_PARENT / "brightspace" / "token.json")))
CREDS_FILE = Path(os.environ.get("BRIGHTSPACE_CREDS_FILE",
                         str(TOKEN_FILE.parent / "credentials.enc")))
OUTPUT_DIR = STATE_PARENT / "brightspace_sync"


def ensure_state_dirs() -> None:
    """Create the state directories. Session cookies, the token and debug dumps are bearer secrets: owner-only."""
    SESSION_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    SESSION_DIR.chmod(0o700)
    TOKEN_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        TOKEN_FILE.chmod(0o600)


def write_private(path: Path, data: str) -> None:
    """Write a file readable only by the owner (also tightens an existing file)."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(data)
    path.chmod(0o600)


def safe_filename(s: str | Path) -> str:
    """Sanitize a string for use as a filename — removes filesystem-unsafe chars."""
    return str(s or "untitled").replace("\\", "_").replace("\n", " ").strip()[:180]
