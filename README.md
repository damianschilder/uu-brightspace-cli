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

Store your credentials encrypted once:

```sh
python3 brightspace-cli.py save-creds
```

This prompts for your Solis-id, password, TOTP secret and a passphrase, and writes
them to `credentials.enc` (scrypt + AES-256-GCM, mode `0600`). Whenever a login is
needed, the CLI asks for the passphrase. To skip the prompt (cron, Docker), set
`BRIGHTSPACE_PASSPHRASE`. Keep the passphrase out of files, or the encryption gains
you nothing.

Or pass the credentials as environment variables, which take precedence over the
saved file:

```sh
export BRIGHTSPACE_SOLISID=...
export BRIGHTSPACE_PASSWORD=...
export BRIGHTSPACE_TOTP_SECRET=...
```

Your password and TOTP secret sit together in the same place, so anyone who gets
both bypasses MFA. Avoid `--password`/`--totp` flags: they show up in `ps` and
shell history.

Optional: `BRIGHTSPACE_ORG_UNIT` (default course), `BRIGHTSPACE_BASE_URL`,
`BRIGHTSPACE_SESSION_DIR`, `BRIGHTSPACE_TOKEN_FILE` and `BRIGHTSPACE_CREDS_FILE`
(default `../brightspace/` next to the repo). The token and session are bearer
secrets and are kept owner-only. To keep them off disk, point them at a tmpfs such
as `$XDG_RUNTIME_DIR`.

### Getting your TOTP secret

The CLI generates MFA codes itself, so it needs the secret key behind your
authenticator entry (e.g. `JBSWY3DPEHPK3PXP`).

[MySolisID](https://mysolisid.uu.nl) allows only one authenticator, so you either
export the secret from your current app or set the authenticator up again.

**Export from your current app.** Aegis, 2FAS, Bitwarden, 1Password and KeePassXC
show the secret in the entry's details or export. Google Authenticator's "Transfer
accounts" QR holds an encoded `otpauth-migration://` URI that needs a decoder tool.

**Or set it up again.**

1. In MySolisID > Two-factor authentication, choose "Deactivate with Authenticator".
2. Activate it again. At the QR code, copy the key shown for manual entry, or decode
   the QR with `zbarimg qr.png` and take the `secret=` value from the `otpauth://` URI.
3. Scan the same QR with your phone's authenticator and finish activation with a code
   from it. Phone and CLI now share the same secret.

## Usage

```sh
python3 brightspace-cli.py save-creds                     # Store credentials encrypted
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

To use saved credentials instead, run `save-creds` once with `-it` against the same
volume. It writes `/data/credentials.enc`. From then on, pass `-e BRIGHTSPACE_PASSPHRASE`
(or use `-it` and type it) instead of the three credential variables.

## Disclaimer

Unofficial tool, not affiliated with or endorsed by Utrecht University or D2L.
Provided as is, without warranty. Use at your own risk.

You are responsible for using it in line with your institution's regulations,
including its IT rules, rules on credentials and MFA, and the copyright on course
materials. Only access content you're authorised to see, and keep downloads for
personal study.
