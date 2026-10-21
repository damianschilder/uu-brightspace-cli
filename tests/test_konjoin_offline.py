"""Konjoin end to end, in a real Chromium, against the offline fake."""

from __future__ import annotations

import json

import pyotp
import pytest

from fake_uu import PASSWORD, PROJECTS, SOLISID, TOTP_SECRET
from uu_cli import auth
from uu_cli.services.brightspace.cli import main as brightspace
from uu_cli.services.konjoin.cli import main as konjoin
from uu_cli.services.konjoin.commands import html_to_text

SLUG = PROJECTS[0]["slug"]


def run(main, argv, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    out, err = capsys.readouterr()
    return exc.value.code, out, err


@pytest.fixture
def at_terminal(monkeypatch):
    """Someone at the terminal reading codes off their phone; returns the prompts they saw."""
    prompts: list[str] = []

    def answer(prompt=""):
        prompts.append(prompt)
        return SOLISID if prompt.startswith("Solis-id") else pyotp.TOTP(TOTP_SECRET).now()

    monkeypatch.setattr(auth, "interactive", lambda: True)
    monkeypatch.setattr("builtins.input", answer)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": prompts.append(prompt) or PASSWORD)
    return prompts


def test_html_to_text_keeps_paragraphs_and_list_items():
    assert html_to_text(PROJECTS[0]["description"]) == (
        "Why does one person develop a neurological disorder & another not?\n"
        "• Clinical genetics\n• Eight weeks")


@pytest.mark.browser
def test_projects_need_no_login(fake_uu, at_terminal, capsys):
    code, out, err = run(konjoin, ["projects"], capsys)

    assert code == 0, err
    assert "Neurogenetics elective" in out and SLUG in out
    assert "Soil microbes" not in out  # on page 2
    assert "Page 1 of 2 · 3 projects" in out
    assert at_terminal == [] and fake_uu.konjoin_logins == 0


@pytest.mark.browser
def test_konjoin_pages_load_only_konjoins_own_files(fake_uu, capsys):
    code, _, err = run(konjoin, ["projects"], capsys)

    assert code == 0, err
    assert fake_uu.elsewhere == []  # the polyfill script and the font never left the browser


@pytest.mark.browser
def test_projects_search_all_pages_as_json(fake_uu, capsys):
    code, out, _ = run(konjoin, ["projects", "--search", "still", "--all", "--json"], capsys)

    assert code == 0
    assert [p["slug"] for p in json.loads(out)] == ["3100-trade-routes-in-still-lifes"]


@pytest.mark.browser
def test_export_writes_every_page(fake_uu, state, capsys):
    target = state / "konjoin" / "projects.json"

    code, out, _ = run(konjoin, ["export", "-o", str(target)], capsys)

    assert code == 0
    assert [p["id"] for p in json.loads(target.read_text())] == [3208, 3100, 2990]
    assert "3 projects" in out


@pytest.mark.browser
def test_export_leaves_out_emails_and_organisation_ids(fake_uu, state, capsys):
    target = state / "projects.json"

    code, out, _ = run(konjoin, ["export", "-o", str(target)], capsys)

    assert code == 0
    saved = target.read_text()
    assert "email" not in saved and "organization_uid" not in saved and "1000001" not in saved
    assert json.loads(saved)[0]["leader"] == {"full_name": "Anoniem"}
    assert "without emails and organisation ids" in out


@pytest.mark.browser
def test_keep_contact_details_keeps_them(fake_uu, state, capsys):
    target = state / "projects.json"

    run(konjoin, ["export", "-o", str(target), "--keep-contact-details"], capsys)

    assert json.loads(target.read_text())[0]["leader"]["email"] == "leader@example.org"


@pytest.mark.browser
def test_project_json_leaves_out_contact_details(fake_uu, at_terminal, capsys):
    code, out, err = run(konjoin, ["project", SLUG, "--json"], capsys)

    assert code == 0, err
    assert json.loads(out)["collaborators"] == [{"full_name": "Dr. A. Example"}]


@pytest.mark.browser
def test_project_details_log_in_through_surfconext(fake_uu, at_terminal, capsys):
    code, out, err = run(konjoin, ["project", SLUG], capsys)

    assert code == 0, err
    assert "SURFconext: choosing Utrecht University" in err
    assert fake_uu.wayf_choices >= 1 and fake_uu.konjoin_logins == 1
    assert at_terminal[-1] == "Code from your authenticator app: "
    assert "Neurogenetics elective" in out
    assert "Dr. A. Example" in out and "• Clinical genetics" in out


@pytest.mark.browser
def test_one_code_covers_brightspace_and_konjoin(fake_uu, at_terminal, monkeypatch, capsys):
    run(brightspace, ["login"], capsys)
    monkeypatch.setattr(auth, "interactive", lambda: False)  # no terminal, no secret

    code, out, err = run(konjoin, ["project", SLUG], capsys)

    assert code == 0, err
    assert "Logged in with your existing UU session." in err
    assert len(fake_uu.codes) == 1
    assert fake_uu.logins == 1 and fake_uu.konjoin_logins == 1
    assert "Neurogenetics elective" in out


@pytest.mark.browser
def test_konjoin_session_is_kept_for_the_next_run(fake_uu, at_terminal, monkeypatch, capsys):
    run(konjoin, ["login"], capsys)
    monkeypatch.setattr(auth, "interactive", lambda: False)

    code, out, err = run(konjoin, ["project", SLUG, "--json"], capsys)

    assert code == 0, err
    assert json.loads(out)["id"] == 3208
    assert fake_uu.konjoin_logins == 1 and len(fake_uu.codes) == 1


@pytest.mark.browser
def test_project_without_a_way_to_log_in_says_why(fake_uu, capsys):
    code, _, err = run(konjoin, ["project", SLUG], capsys)

    assert code == 1
    assert "a terminal to type the code" in err
    assert fake_uu.konjoin_logins == 0
