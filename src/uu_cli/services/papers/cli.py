"""`uu papers <command>`: articles from journals UU subscribes to."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from uu_cli import auth, browser, paths
from uu_cli.services.papers import articles, elsevier, library

# Between two articles from Elsevier's API: one researcher's pace, not a crawler's.
PAUSE_S = 1.0


def cmd_open(args) -> int:
    """Open an article through UU's library in a window; you open or download the PDF there."""
    if not auth.has_screen():
        print("ERROR: `uu papers open` needs a screen to open its window on "
              "(DISPLAY or WAYLAND_DISPLAY is not set).", file=sys.stderr)
        return 1
    try:
        url = articles.article_url(args.article)
    except ValueError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    out = Path(args.output)
    print("[LIBRARY] Opening the article through UU's library. Log in there if UU asks, then "
          f"open or download the PDF; it's saved to {out}/.", file=sys.stderr)

    with sync_playwright() as pw:
        ctx = browser.launch(pw, args.session_dir)
        try:
            saved = library.open_article(ctx, url, out, articles.doi_of(args.article),
                                         keep_open=args.keep_open)
        finally:
            browser.save_session(ctx, args.session_dir)
    if not saved:
        print("No PDF saved.", file=sys.stderr)
        return 1
    return 0


def cmd_elsevier(args) -> int:
    """Download Elsevier articles through Elsevier's API."""
    key = os.environ.get("ELSEVIER_API_KEY", "")
    if not key:
        print("ERROR: set ELSEVIER_API_KEY to your API key from "
              "https://dev.elsevier.com/apikey/manage", file=sys.stderr)
        return 1
    token = os.environ.get("ELSEVIER_INSTTOKEN", "")
    out = Path(args.output)
    failed = 0
    for i, ref in enumerate(args.articles):
        doi = articles.doi_of(ref)
        if not doi:
            print(f"{ref}: not a DOI", file=sys.stderr)
            failed += 1
            continue
        if i:
            time.sleep(PAUSE_S)
        try:
            if elsevier.entitled(doi, key, token) is False:
                raise elsevier.ElsevierError(elsevier.NO_ACCESS)
            path = articles.save_pdf(out, elsevier.fetch_pdf(doi, key, token), doi)
        except elsevier.ElsevierError as err:
            print(f"{doi}: {err}", file=sys.stderr)
            failed += 1
            continue
        except OSError as err:  # no network, a proxy, TLS
            print(f"{doi}: could not reach Elsevier: {err}", file=sys.stderr)
            failed += 1
            continue
        print(f"Saved: {path}")
    return 1 if failed else 0


COMMANDS = {"open": cmd_open, "elsevier": cmd_elsevier}


def main(argv: list[str] | None = None, prog: str | None = None) -> None:
    paths.ensure_state_dirs()
    p = argparse.ArgumentParser(
        prog=prog, description="Articles from journals UU subscribes to, through UU's library")
    sub = p.add_subparsers(dest="cmd", required=True)

    op = sub.add_parser("open", help="Open an article through UU's library in a browser window; "
                                     "the PDF you open or download there is saved")
    op.add_argument("article", help="A DOI (10.1016/…) or the article's web address")
    op.add_argument("-o", "--output", default=".", help="Folder for the PDF (default: here)")
    op.add_argument("--keep-open", action="store_true",
                    help="Keep the window open after the first PDF, until you close it")
    op.add_argument("--session-dir", default=str(paths.SESSION_DIR),
                    help="Browser profile, shared with the other services (one UU login)")

    el = sub.add_parser("elsevier", help="Download Elsevier articles through Elsevier's API "
                                         "(ELSEVIER_API_KEY; full text from UU's network)")
    el.add_argument("articles", nargs="+", help="DOIs of Elsevier articles")
    el.add_argument("-o", "--output", default=".", help="Folder for the PDFs (default: here)")

    args = p.parse_args(argv)
    sys.exit(COMMANDS[args.cmd](args))
