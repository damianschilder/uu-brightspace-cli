"""uu papers: an article through UU's library in a window, or from Elsevier's API."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from fake_uu import ARTICLE_PDF
from uu_cli.services.brightspace.cli import main as brightspace
from uu_cli.services.papers import articles, elsevier, library
from uu_cli.services.papers.cli import main as papers

DOI = "10.1016/j.knosys.2025.113564"
PDF_NAME = "10.1016_j.knosys.2025.113564.pdf"


def run(main, argv, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    out, err = capsys.readouterr()
    return exc.value.code, out, err


@pytest.mark.parametrize("ref, doi", [
    (DOI, DOI),
    (f"doi:{DOI}", DOI),
    (f"https://doi.org/{DOI}", DOI),
    ("https://link.springer.com/article/10.1007/s10462-023-10512-3?x=1", "10.1007/s10462-023-10512-3"),
    (f"https://doi.org/{DOI}.", DOI),
    ("https://www.sciencedirect.com/science/article/pii/S0950705125006100", None),
])
def test_doi_of(ref, doi):
    assert articles.doi_of(ref) == doi


def test_the_proxy_link_picks_uu_and_carries_the_article():
    assert library.proxy_url(articles.article_url(DOI)) == (
        f"https://utrechtuniversity.idm.oclc.org/login?auth=uushibboleth&url=https://doi.org/{DOI}")


def test_the_same_pdf_twice_is_one_file(tmp_path):
    first = articles.save_pdf(tmp_path, b"%PDF one", DOI)
    assert articles.save_pdf(tmp_path, b"%PDF one", DOI) == first
    assert articles.save_pdf(tmp_path, b"%PDF two", DOI).name == "10.1016_j.knosys.2025.113564-2.pdf"


# ── uu papers open: the library proxy in a window ─────────────────────────────

@pytest.mark.browser
def test_open_logs_in_at_the_library_and_saves_the_pdf_you_open(window, fake_uu, state, capsys):
    code, out, err = run(papers, ["open", DOI, "-o", str(state / "papers")], capsys)

    assert code == 0, err
    assert (state / "papers" / PDF_NAME).read_bytes() == ARTICLE_PDF
    assert f"Saved: {state / 'papers' / PDF_NAME}" in out
    assert fake_uu.library_links == [f"auth=uushibboleth&url=https://doi.org/{DOI}"]
    assert fake_uu.library_logins == 1 and len(fake_uu.codes) == 1  # you logged in, in the window
    assert len(window) == 1 and not window[0].browser.is_connected()


@pytest.mark.browser
def test_open_needs_no_login_while_uus_session_lasts(window, fake_uu, state, capsys):
    run(brightspace, ["login", "--auth", "browser"], capsys)

    code, _, err = run(papers, ["open", DOI, "-o", str(state / "papers")], capsys)

    assert code == 0, err
    assert len(fake_uu.codes) == 1  # only the Brightspace login asked for one
    assert fake_uu.library_logins == 1


@pytest.mark.browser
def test_the_library_session_is_kept_for_the_next_article(window, fake_uu, state, capsys):
    run(papers, ["open", DOI, "-o", str(state / "papers")], capsys)

    code, _, err = run(papers, ["open", DOI, "-o", str(state / "papers")], capsys)

    assert code == 0, err
    assert fake_uu.library_logins == 1  # the second run went straight to the article


@pytest.mark.browser
@pytest.mark.parametrize("window", [False], indirect=True)
def test_open_gives_up_without_a_pdf(window, fake_uu, state, monkeypatch, capsys):
    monkeypatch.setattr(library, "WINDOW_TIMEOUT_S", 1)

    code, _, err = run(papers, ["open", DOI, "-o", str(state / "papers")], capsys)

    assert code == 1 and "No PDF saved" in err
    assert not (state / "papers").exists()
    assert len(window) == 1 and not window[0].browser.is_connected()


def test_open_needs_a_screen(monkeypatch, capsys):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    code, _, err = run(papers, ["open", DOI], capsys)

    assert code == 1 and "needs a screen" in err


# ── uu papers elsevier: Elsevier's API ────────────────────────────────────────

@pytest.fixture
def api(monkeypatch):
    """Elsevier's API: answers maps a url prefix to (status, headers, body); calls lists requests."""
    api = SimpleNamespace(calls=[], answers={
        f"{elsevier.API}/entitlement/doi/": (200, {}, json.dumps(
            {"entitlement-response": {"document-entitlement": {"entitled": True}}}).encode()),
        f"{elsevier.API}/doi/": (200, {"content-type": "application/pdf"}, ARTICLE_PDF),
    })

    def get(url, headers):
        api.calls.append((url, headers))
        return next(answer for prefix, answer in api.answers.items() if url.startswith(prefix))

    monkeypatch.setattr(elsevier, "_get", get)
    monkeypatch.setattr("uu_cli.services.papers.cli.PAUSE_S", 0)
    monkeypatch.setenv("ELSEVIER_API_KEY", "k3y")
    return api


def test_elsevier_saves_the_pdf(api, state, capsys):
    code, out, err = run(papers, ["elsevier", f"https://doi.org/{DOI}", "-o", str(state)], capsys)

    assert code == 0, err
    assert (state / PDF_NAME).read_bytes() == ARTICLE_PDF
    assert [url for url, _ in api.calls] == [f"{elsevier.API}/entitlement/doi/{DOI}",
                                             f"{elsevier.API}/doi/{DOI}"]
    assert all(headers["X-ELS-APIKey"] == "k3y" for _, headers in api.calls)


def test_elsevier_stops_when_you_have_no_access(api, state, capsys):
    api.answers[f"{elsevier.API}/entitlement/doi/"] = (200, {}, json.dumps(
        {"entitlement-response": {"document-entitlement": {"entitled": False}}}).encode())

    code, _, err = run(papers, ["elsevier", DOI, "-o", str(state)], capsys)

    assert code == 1 and "eduroam" in err and "uu papers open" in err
    assert len(api.calls) == 1  # no PDF requested
    assert not (state / PDF_NAME).exists()


def test_elsevier_follows_a_redirect_without_the_key(api, state, capsys):
    api.answers[f"{elsevier.API}/doi/"] = (303, {"location": "https://cdn.example/x.pdf"}, b"")
    api.answers["https://cdn.example/"] = (200, {"content-type": "application/pdf"}, ARTICLE_PDF)

    code, _, err = run(papers, ["elsevier", DOI, "-o", str(state)], capsys)

    assert code == 0, err
    url, headers = api.calls[-1]
    assert url == "https://cdn.example/x.pdf" and "X-ELS-APIKey" not in headers


def test_elsevier_says_what_a_refusal_means(api, state, capsys):
    api.answers[f"{elsevier.API}/entitlement/doi/"] = (401, {}, b"")
    api.answers[f"{elsevier.API}/doi/"] = (401, {}, b"")

    code, _, err = run(papers, ["elsevier", DOI, "-o", str(state)], capsys)

    assert code == 1 and "ELSEVIER_API_KEY" in err


def test_elsevier_needs_a_key(capsys):
    code, _, err = run(papers, ["elsevier", DOI], capsys)

    assert code == 1 and "ELSEVIER_API_KEY" in err and "dev.elsevier.com" in err
