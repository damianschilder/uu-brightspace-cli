# Brightspace CLI

Headless Brightspace (D2L) course-sync CLI (Playwright).

Built specifically for Utrecht University's Brightspace instance (https://uu.brightspace.com).

Log in with your SolisID + MFA (TOTP) and mirror the full contents of your enrolled
Brightspace courses - slides, PDFs, documents, assignment instructions, files linked
from inside pages, and schedules - to a local directory. You can also query your
courses, assignments, grades, and announcements from the command line.

## Features

- **Download an entire course** - `sync` walks every module and topic and mirrors the
  content to disk: file attachments (PDF, PPTX, DOCX, XLSX, …), inline content pages,
  and assignment instructions with the files they link to.
- **Sync every enrolled course** - `sync-all` skips group/team sections and supports
  `--dry-run` and `-o/--output`.
- **Follow linked files** - it also downloads files referenced from inside saved content
  pages (e.g. a lecture PDF embedded in a page), so you get the whole module, not just
  the top-level entries.
- **Schedules and deadlines** - detects Google Sheets schedules linked in course content,
  downloads them as CSV, and merges their deadlines with native Brightspace dropbox due dates.
- **Incremental** - files already on disk are skipped, so re-running a sync is cheap.
- **Headless authentication over MFA** - logs in non-interactively with SolisID + TOTP and
  caches the browser session and bearer token.
- **Course queries** - list enrolled courses, a course's table of contents, assignments
  (dropbox + LTI links), grades, and announcements.
- **Docker-ready** - build the bundled image and run it with your env and a mounted state volume.

## Limitations

- **TOTP only, no push notifications.** Login works only if your Solis-id MFA uses a
  time-based code (TOTP) from an authenticator app you set up yourself (Aegis, 2FAS,
  Google Authenticator, Bitwarden, 1Password, etc.). If you approve logins with a push
  notification in the university's app, the CLI can't log in: it has no way to tap
  "approve". You need to enrol a TOTP authenticator as an MFA method (see
  [Getting your TOTP secret](#getting-your-totp-secret)).
- **UU only.** The login flow is written for Utrecht University's Solis-id login page.
  Other institutions' Brightspace instances use different login pages and won't work
  without code changes.
- **Can break without warning.** The CLI drives the login pages and Brightspace in a
  headless browser. If UU or D2L changes those pages, login or sync may stop working
  until the code is updated.

## Getting your TOTP secret

The CLI generates MFA codes itself, so it needs the secret key behind your
authenticator entry. This is the same key your authenticator app stores when you scan
the QR code. It is usually a string of 16 to 32 letters A-Z and digits 2-7, e.g.
`JBSWY3DPEHPK3PXP`.

**Option A: enrol a new authenticator (recommended)**

1. Sign in to UU's MFA / Solis-id self-service page (check the UU IT help pages for the
   current link) and choose to add a new authenticator app (TOTP) method.
2. When the QR code appears, look for a link like "Can't scan?" or "Enter key
   manually". It shows the secret as text. Copy it.
3. If only a QR code is shown, save it as an image and decode it, e.g.
   `zbarimg qr.png`. You get a URI like
   `otpauth://totp/UU:solisid?secret=JBSWY3DPEHPK3PXP&issuer=UU`. The value after
   `secret=` is your secret.
4. Also add the same secret (or QR code) to an authenticator app on your phone, so you
   can still log in by hand. Finish the enrolment with a code from that app.

**Option B: export from an authenticator you already use**

Some apps can show or export existing secrets:
- **Aegis / 2FAS:** export the vault (unencrypted, temporarily) or open the entry's
  details. The secret is in the export file.
- **Bitwarden / 1Password / KeePassXC:** edit the entry and copy the TOTP/OTP field.
- **Google Authenticator:** "Transfer accounts" gives a QR with an
  `otpauth-migration://` URI. That URI is encoded, so you need a decoder tool to get
  the secret out. Option A is usually easier.
- **Push-only apps** generally don't expose a secret. Use Option A.

**Check it** before you run the CLI. This prints the current code; compare it with
your phone:

```sh
python3 -c "import pyotp, os; print(pyotp.TOTP(os.environ['BRIGHTSPACE_TOTP_SECRET']).now())"
```

**Keep it safe.** Anyone who has your password and this secret can pass your MFA.
Don't commit it, paste it into chats or issues, or leave it in shell history: put the
`export` lines in a file only you can read (`chmod 600`), outside the repo. If you
think the secret has leaked, remove that authenticator from your MFA settings and
enrol a new one.

## Requirements and install

Python 3.10+, pip, and Chromium with its system dependencies.

```sh
pip install -r requirements.txt
playwright install chromium
```

## Configuration

Set environment variables in your shell before running the CLI.
No credentials are stored in the repo. Login caches browser state and a token
at the configured paths; keep these files outside the repository.

| Variable | Purpose / default |
| --- | --- |
| `BRIGHTSPACE_SOLISID` | Login username. |
| `BRIGHTSPACE_PASSWORD` | Login password. |
| `BRIGHTSPACE_TOTP_SECRET` | Secret used to generate MFA codes. |
| `BRIGHTSPACE_ORG_UNIT` | Course org unit for content commands; alternatively use `--org-unit`. |
| `BRIGHTSPACE_BASE_URL` | Brightspace server URL; defaults to `https://uu.brightspace.com`. |
| `BRIGHTSPACE_SESSION_DIR` | Persistent browser profile; defaults to `../brightspace/session` relative to the script directory. |
| `BRIGHTSPACE_TOKEN_FILE` | Cached token file; defaults to `../brightspace/token.json` relative to the script directory. |

## Usage

Single-course commands below (including `sync`) require the course's org-unit id, passed as `--org-unit <id>` or set via `BRIGHTSPACE_ORG_UNIT`; without it, `sync` exits with an error.

```sh
python3 brightspace-cli.py login                 # Authenticate and cache a token
python3 brightspace-cli.py courses               # List enrolled courses
python3 brightspace-cli.py toc                   # Show course table of contents
python3 brightspace-cli.py assignments           # List dropbox assignments and LTI links
python3 brightspace-cli.py grades                # Show grades
python3 brightspace-cli.py news                  # Show announcements
python3 brightspace-cli.py schedule -o ./output  # Download linked Google Sheets
python3 brightspace-cli.py deadlines             # Show upcoming deadlines
python3 brightspace-cli.py sync --org-unit <id> -o ./output  # Download ALL contents of ONE course (id required)
python3 brightspace-cli.py sync-all -o ./output  # Sync every enrolled course
python3 brightspace-cli.py sync-all --dry-run    # Preview courses without downloading
```

`sync` downloads the **entire** course, so you must tell it which one:
`python3 brightspace-cli.py sync --org-unit <id> -o ./output` (or set `BRIGHTSPACE_ORG_UNIT`).
It walks every module and topic and mirrors the content into `<output>/<org-unit>/`: file
attachments (PDF, PPTX, DOCX, XLSX, …), inline content pages, files linked from inside those
pages, assignment instructions, and any Google Sheets schedules. Re-run any time - files
already downloaded are skipped, so you can keep a local copy of the course up to date.

`sync-all` discovers enrolled course offerings automatically and uses the same output
layout as `sync`. It continues if a
course fails, prints a per-course summary, and exits nonzero if any course failed.

Run `python3 brightspace-cli.py --help` for global options, or append `--help`
to a subcommand for its options.

## Docker

The [Dockerfile](Dockerfile) uses the Playwright image with Chromium installed.
Build it, then pass environment variables from your shell and mount persistent
state at `/data`. The image sets the session and token paths shown below.

```sh
docker build -t brightspace-cli .
docker run --rm \
  -e BRIGHTSPACE_SOLISID \
  -e BRIGHTSPACE_PASSWORD \
  -e BRIGHTSPACE_TOTP_SECRET \
  -e BRIGHTSPACE_ORG_UNIT \
  -e BRIGHTSPACE_BASE_URL="${BRIGHTSPACE_BASE_URL:-https://uu.brightspace.com}" \
  -e BRIGHTSPACE_SESSION_DIR=/data/session \
  -e BRIGHTSPACE_TOKEN_FILE=/data/token.json \
  -v brightspace-state:/data \
  -v "$PWD/output:/output" \
  brightspace-cli sync -o /output
```

Replace `sync -o /output` with `login` to authenticate explicitly, or with
another subcommand. Reuse the state volume across runs.

## Disclaimer

This is an unofficial, community tool. It is NOT affiliated with, endorsed by,
or supported by Utrecht University, D2L / Brightspace, or any other institution.
"Utrecht University", "Solis-id" and "Brightspace" are used only to describe what
the tool works with.

It is provided AS IS, with no warranty. There is NO guarantee that it works,
keeps working, or produces correct results. Use at your own risk.

You are responsible for using it in accordance with your institution's regulations,
including Utrecht University's IT acceptable-use rules, its rules on handling your
account credentials and MFA, and the copyright and terms of use of course materials.
Only access courses and content you are authorised to access. Downloaded materials
are for your personal study. Don't redistribute them unless the rights holder allows
it. If you're unsure whether something is allowed, ask your institution first.
