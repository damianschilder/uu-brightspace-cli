"""--auth browser: you log in yourself in a browser window, and the CLI takes the session over."""

from __future__ import annotations

import json
import sys
from argparse import Namespace

import pytest
from playwright.sync_api import BrowserContext

from fake_uu import PROJECTS
from uu_cli import auth, browser, login, paths
from uu_cli.services.brightspace.cli import main as brightspace
from uu_cli.services.konjoin.cli import main as konjoin


def run(main, argv, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    out, err = capsys.readouterr()
    return exc.value.code, out, err


@pytest.fixture
def window(request, fake_uu, monkeypatch):
    """The window --auth browser opens, headless here; returns the windows opened.

    By default you fill in UU's forms in it; parametrize with False for a window nobody uses.
    """
    by_hand = getattr(request, "param", True)
    opened = []
    real_open_window = browser.open_window

    def open_window(ctx):
        win = real_open_window(ctx, headless=True)
        fake_uu.install(win, by_hand=by_hand)
        opened.append(win)
        return win

    monkeypatch.setattr(browser, "open_window", open_window)
    monkeypatch.setenv("DISPLAY", ":0")
    return opened


def test_browser_route_needs_a_screen(monkeypatch, capsys):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    assert not auth.ready_to_login(Namespace(auth="browser"))
    assert "needs a screen" in capsys.readouterr().err


def test_browser_route_asks_for_nothing(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail(f"asked {prompt!r}"))

    # No Solis-id, password or secret on args: the route never looks for them.
    assert auth.ready_to_login(Namespace(auth="browser"))


@pytest.mark.browser
def test_you_log_in_in_the_window_and_the_cli_takes_over(window, fake_uu, capsys):
    code, _, err = run(brightspace, ["login", "--auth", "browser"], capsys)

    assert code == 0, err
    assert len(window) == 1 and "Log in to UU in the browser window" in err
    assert fake_uu.logins == 1 and len(fake_uu.codes) == 1  # the code went in the window
    assert json.loads(paths.TOKEN_FILE.read_text())["token"] == fake_uu.token
    assert not window[0].browser.is_connected()  # closed once the CLI had the session


@pytest.mark.browser
def test_window_opens_where_playwright_gives_the_cli_no_browser(window, fake_uu, monkeypatch,
                                                                 capsys):
    # Older Playwright versions: the CLI's persistent context has no .browser.
    real = BrowserContext.browser
    monkeypatch.setattr(BrowserContext, "browser",
                        property(lambda c: None if c in browser._launched_by else real.fget(c)))

    code, _, err = run(brightspace, ["login", "--auth", "browser"], capsys)

    assert code == 0, err
    assert len(window) == 1 and fake_uu.logins == 1


@pytest.mark.browser
def test_no_window_while_uus_session_lasts(window, fake_uu, capsys):
    run(brightspace, ["login", "--auth", "browser"], capsys)

    code, out, err = run(konjoin, ["project", PROJECTS[0]["slug"], "--auth", "browser"], capsys)

    assert code == 0, err
    assert len(window) == 1  # only the Brightspace login opened one
    assert fake_uu.konjoin_logins == 1 and len(fake_uu.codes) == 1
    assert "Neurogenetics elective" in out


@pytest.mark.browser
@pytest.mark.parametrize("window", [False], indirect=True)
def test_window_gives_up_and_closes_when_nobody_logs_in(window, fake_uu, monkeypatch):
    monkeypatch.setattr(login, "WINDOW_TIMEOUT_S", 1)

    with pytest.raises(RuntimeError, match="No login in the browser window"):
        brightspace(["login", "--auth", "browser"])

    assert len(window) == 1 and not window[0].browser.is_connected()
    assert fake_uu.logins == 0
