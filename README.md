# Brightspace CLI

Headless CLI for [Utrecht University's Brightspace](https://uu.brightspace.com). Logs in
with your Solis-id + TOTP and mirrors your courses to a local folder: slides, PDFs,
assignment instructions, linked files and schedules. It can also list courses,
assignments, deadlines, grades and announcements.

## Features

- **Full course sync** of every module and topic, including files linked from inside pages.
- **All courses at once** with `sync-all` (skips group/team sections).
- **Deadlines** from Brightspace dropboxes merged with linked Google Sheets schedules.
- **Incremental**: files already on disk are skipped.
- **Headless login** with cached session and token.

## Limitations

- **TOTP only.** You need MFA codes from an authenticator app you set up yourself.
  The UU push-notification approval won't work.
- **UU only.** The login flow is written for UU's Solis-id login page.
- **Can break** if UU or D2L change their pages.

## Install

Python 3.10+ and Chromium.

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium
```

## Configuration

```sh
export BRIGHTSPACE_SOLISID=...
export BRIGHTSPACE_PASSWORD=...
export BRIGHTSPACE_TOTP_SECRET=...
```

Optional: `BRIGHTSPACE_ORG_UNIT` (default course), `BRIGHTSPACE_BASE_URL`,
`BRIGHTSPACE_SESSION_DIR` and `BRIGHTSPACE_TOKEN_FILE` (default `../brightspace/`
next to the repo).

### Getting your TOTP secret

The CLI generates MFA codes itself, so it needs the secret key behind your
authenticator entry (e.g. `JBSWY3DPEHPK3PXP`).

1. In UU's MFA / Solis-id self-service page, add a new authenticator app (TOTP).
2. At the QR code, click "Can't scan?" / "Enter key manually" and copy the key. Or
   decode the QR with `zbarimg qr.png` and take the `secret=` value from the
   `otpauth://` URI.
3. Add the same key to your phone's authenticator too, and finish enrolment with it.

Already using Aegis, 2FAS, Bitwarden, 1Password or KeePassXC? You can copy the secret
from the entry.

## Usage

```sh
python3 brightspace-cli.py login                          # Authenticate and cache a token
python3 brightspace-cli.py courses                        # List enrolled courses
python3 brightspace-cli.py sync --org-unit <id> -o out    # Download one course
python3 brightspace-cli.py sync-all -o out                # Download every course
python3 brightspace-cli.py sync-all --dry-run             # Preview without downloading
python3 brightspace-cli.py deadlines                      # Upcoming deadlines
python3 brightspace-cli.py assignments | grades | news | toc | schedule
```

All commands except `login`, `courses` and `sync-all` need a course's org-unit id:
pass `--org-unit <id>` (find ids with `courses`) or set `BRIGHTSPACE_ORG_UNIT`.
Output goes to `<out>/<org-unit>/`. Run with `--help` for all options.

## Docker

```sh
docker build -t brightspace-cli .
docker run --rm \
  -e BRIGHTSPACE_SOLISID -e BRIGHTSPACE_PASSWORD -e BRIGHTSPACE_TOTP_SECRET \
  -e BRIGHTSPACE_SESSION_DIR=/data/session -e BRIGHTSPACE_TOKEN_FILE=/data/token.json \
  -v brightspace-state:/data -v "$PWD/output:/output" \
  brightspace-cli sync-all -o /output
```

## Disclaimer

Unofficial tool, not affiliated with or endorsed by Utrecht University or D2L.
Provided as is, without warranty. Use at your own risk.

You are responsible for using it in line with your institution's regulations,
including its IT rules, rules on credentials and MFA, and the copyright on course
materials. Only access content you're authorised to see, and keep downloads for
personal study.
