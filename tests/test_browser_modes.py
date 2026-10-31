"""BRW-07 step 2: browser modes (chromium | chrome | attach).

Unit tests need no Chrome. Tests marked real_chrome start the installed Chrome with a throwaway
profile on a free port; they run only with RUN_REAL_CHROME=1 and never touch AGENT_PROFILE_DIR.
"""
import asyncio
import http.server
import os
import socket
import subprocess
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright.async_api")

from app import browser as browser_mod  # noqa: E402
from app import config  # noqa: E402
from app.browser import (BrowserController, BrowserStartError, cdp_version, chrome_command,  # noqa: E402
                         find_chrome, wait_for_cdp)

real_chrome = pytest.mark.skipif(os.getenv("RUN_REAL_CHROME") != "1",
                                 reason="set RUN_REAL_CHROME=1 to start the installed Chrome")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fake_exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    return path


# Chrome-path detection

def test_chrome_path_setting_wins(tmp_path):
    exe = fake_exe(tmp_path / "my" / "chrome.exe")
    assert find_chrome(str(exe), platform="win32", env={}) == str(exe)
    assert find_chrome(str(tmp_path / "missing.exe"), platform="win32", env={}) is None


def test_windows_install_locations_in_order(tmp_path):
    env = {"PROGRAMFILES": str(tmp_path / "pf"), "PROGRAMFILES(X86)": str(tmp_path / "pf86"),
           "LOCALAPPDATA": str(tmp_path / "local")}
    assert find_chrome("", platform="win32", env=env) is None
    local = fake_exe(tmp_path / "local" / "Google" / "Chrome" / "Application" / "chrome.exe")
    assert find_chrome("", platform="win32", env=env) == str(local)
    pf = fake_exe(tmp_path / "pf" / "Google" / "Chrome" / "Application" / "chrome.exe")
    assert find_chrome("", platform="win32", env=env) == str(pf)   # Program Files first


def test_macos_user_applications(tmp_path):
    app = fake_exe(tmp_path / "Applications" / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome")
    assert find_chrome("", platform="darwin", env={"HOME": str(tmp_path)}) == str(app)


def test_linux_uses_which(tmp_path, monkeypatch):
    exe = fake_exe(tmp_path / "google-chrome")
    monkeypatch.setattr(browser_mod.shutil, "which", lambda name: str(exe) if name == "google-chrome" else None)
    assert find_chrome("", platform="linux", env={}) == str(exe)
    monkeypatch.setattr(browser_mod.shutil, "which", lambda name: None)
    assert find_chrome("", platform="linux", env={}) is None


# Launch command

def test_chrome_command(tmp_path):
    cmd = chrome_command("chrome.exe", 9333, tmp_path / "profile", "https://mail.google.com")
    assert cmd == ["chrome.exe", "--remote-debugging-port=9333", f"--user-data-dir={tmp_path / 'profile'}",
                   "--no-first-run", "--no-default-browser-check", "https://mail.google.com"]
    joined = " ".join(cmd)
    assert "--remote-debugging-address" not in joined          # stays on loopback
    assert "AutomationControlled" not in joined and "user-agent" not in joined   # no evasion
    assert chrome_command("c", 1, "p")[-1] == "about:blank"


# Mode selection

def test_mode_defaults_to_config(monkeypatch):
    monkeypatch.setattr(config, "BROWSER_MODE", "attach")
    assert BrowserController().mode == "attach"
    monkeypatch.setattr(config, "BROWSER_MODE", "chromium")
    assert BrowserController().mode == "chromium"
    assert BrowserController(mode="chrome").mode == "chrome"


def test_bad_mode_is_rejected():
    with pytest.raises(ValueError, match="chromium, chrome, attach"):
        BrowserController(mode="firefox")


def test_debug_port_is_loopback_only():
    b = BrowserController(mode="chrome", debug_port=9444)
    assert b.cdp_url == "http://127.0.0.1:9444"
    assert BrowserController(mode="chrome").cdp_url == config.CDP_URL


async def test_attach_with_nothing_listening_gives_clear_error():
    port = free_port()
    b = BrowserController(mode="attach", debug_port=port)
    with pytest.raises(BrowserStartError, match=f"No Chrome is listening on http://127.0.0.1:{port}"):
        await b.start()
    assert b._pw is None and b._browser is None   # start() cleaned up after itself


async def test_chrome_mode_without_chrome_installed(tmp_path):
    b = BrowserController(mode="chrome", debug_port=free_port(), profile_dir=tmp_path / "p",
                          chrome_path=str(tmp_path / "no-chrome.exe"))
    with pytest.raises(BrowserStartError, match="Chrome was not found"):
        await b.start()


def test_wait_for_cdp_times_out():
    with pytest.raises(BrowserStartError, match="did not answer"):
        wait_for_cdp(f"http://127.0.0.1:{free_port()}", seconds=0.5)
    assert cdp_version(f"http://127.0.0.1:{free_port()}") is None


# Real Chrome (RUN_REAL_CHROME=1)

PAGES = {
    "/console": "<title>Voice Console</title><textarea id=box></textarea><button>x</button>",
    "/one": "<title>Page one</title><a id=popup href='/two' target='_blank' rel=noopener>open two</a>",
    "/two": "<title>Page two</title><p>second</p>",
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path, "not found")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


async def wait_for(condition, timeout=10.0):
    for _ in range(int(timeout / 0.1)):
        if condition():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("condition not met in time")


@real_chrome
async def test_chrome_mode_end_to_end(site, tmp_path):
    announced = []
    profile = tmp_path / "profile"
    b = BrowserController(on_new_tab=lambda t, u: announced.append(t), console_url=f"{site}/console",
                          mode="chrome", debug_port=free_port(), profile_dir=profile)
    await b.start()
    try:
        assert b._proc is not None                       # we started this Chrome
        ctx = b._browser.contexts[0]                     # the profile's default context
        assert b.console_page in ctx.pages and b.active in ctx.pages
        assert await b._window_id(b.console_page) != await b._window_id(b.active)   # own windows
        assert len(await b.list_tabs()) == 1

        await b.goto(f"{site}/one")
        await b.active.click("#popup")                   # target=_blank, rel=noopener
        await wait_for(lambda: announced)
        assert announced == ["Page two"]
        assert [t["title"] for t in await b.list_tabs()] == ["Page one", "Page two"]

        await b.switch_tab(0)
        assert b.active.url == f"{site}/one"
        await b.close_tab(1)
        await b.close_tab(0)                             # last tab: a fresh agent window opens
        tabs = await b.list_tabs()
        assert len(tabs) == 1 and b._agent_window is not None

        await b.console_page.focus("button")
        await b.refocus_console()
        assert await b.console_page.evaluate("document.activeElement.tagName") == "TEXTAREA"

        # A tab the user opens in another window is not an agent tab.
        session = await b._browser.new_browser_cdp_session()
        await session.send("Target.createTarget", {"url": f"{site}/two", "newWindow": True})
        await asyncio.sleep(1.5)
        assert len(await b.list_tabs()) == 1 and len(announced) == 1
    finally:
        await b.close()
    assert cdp_version(b.cdp_url) is None                # the Chrome we started is gone
    assert profile.is_dir() and any(profile.iterdir())   # its profile folder stays


@real_chrome
async def test_attach_mode_never_kills_chrome(site, tmp_path):
    port = free_port()
    chrome = find_chrome()
    proc = subprocess.Popen(chrome_command(chrome, port, tmp_path / "profile"))
    try:
        wait_for_cdp(f"http://127.0.0.1:{port}")
        b = BrowserController(console_url=f"{site}/console", mode="attach", debug_port=port)
        await b.start()
        assert b._proc is None
        await b.goto(f"{site}/one")
        assert (await b.list_tabs())[0]["title"] == "Page one"
        await b.close()
        assert cdp_version(f"http://127.0.0.1:{port}") is not None   # still running
    finally:
        proc.terminate()
        proc.wait(timeout=15)
