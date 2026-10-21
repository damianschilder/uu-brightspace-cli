"""Google Sheets schedules linked from course content, and the deadlines in them."""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import requests


def extract_google_sheets_urls(text: str) -> list[str]:
    """Extract Google Sheets URLs from any text (HTML, plain text, JSON)."""
    urls = []
    for match in re.finditer(
        r"https://docs\.google\.com/spreadsheets/d/[\w\-]+/edit[^\s\)\]\}\"]*",
        text
    ):
        url = match.group(0).rstrip("/")
        # Convert edit URL to export CSV URL
        spreadsheet_id = url.split("/d/")[1].split("/")[0] if "/d/" in url else None
        if spreadsheet_id:
            export_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid=0"
            urls.append(export_url)
    return urls


def download_google_sheet(csv_url: str, dest: Path, label: str = "") -> bool:
    """Download a Google Sheet as CSV. Returns True on success."""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(csv_url, timeout=30)
        if resp.ok and len(resp.content) > 50:
            dest.write_bytes(resp.content)
            print(f"  ✓ {label or dest.name}", file=sys.stderr)
            return True
        else:
            print(f"  ! {label}: HTTP {resp.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"  ! {label}: {e}", file=sys.stderr)
    return False


def parse_sheet_deadlines(csv_path: Path) -> list[dict]:
    """Read the schedule CSV and return events as (date, title) rows.

    Priority: Deadline column > Topic column > first non-empty cell in the row.
    Dates are expected in the 'Date' column (e.g. "April 21, 2026Tue").
    """
    deadlines = []
    month_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                 "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
    try:
        with open(csv_path, encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                date_str = row.get("Date", "").strip()
                if not date_str:
                    continue
                # Parse "Month Day, Year[DayOfWeek]" e.g. "April 21, 2026Tue"
                m = re.search(
                    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})",
                    date_str, re.I)
                if not m:
                    continue
                mon, day, year = m.groups()
                month = month_map.get(mon[:3].lower(), 1)
                iso = f"{year}-{month:02d}-{int(day):02d}"

                # Title priority: explicit Deadline field > Topic > first non-empty cell
                title = row.get("Deadline", "").strip()
                if not title:
                    title = row.get("Topic", "").strip().split("\n")[0]
                if not title:
                    for v in row.values():
                        if v.strip() and v.strip() != date_str:
                            title = v.strip().split("\n")[0]
                            break

                deadlines.append({"date": iso, "title": title, "raw": date_str})
    except Exception as e:
        print(f"  ! Failed to parse {csv_path}: {e}", file=sys.stderr)
    return deadlines
