#!/usr/bin/env python3
"""Compatibility entry point: `python3 brightspace-cli.py <command>` is `uu brightspace <command>`."""

import sys
from pathlib import Path

# Runs from a plain checkout too, without `pip install -e .`.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from uu_cli.services.brightspace.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
