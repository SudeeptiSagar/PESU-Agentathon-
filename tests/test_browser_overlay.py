"""CONSOLE_MODE=overlay: the Voice Console is the native floating orb, so the agent browser opens no Console window of its own,
and "refocus the Console" brings the overlay (found by its window title) to the front."""
import sys

import pytest

pytest.importorskip("playwright.async_api")

from app import browser as browser_mod  # noqa: E402
from app import config  # noqa: E402
from app.browser import BrowserController  # noqa: E402


def test_the_console_mode_must_be_known():
    with pytest.raises(ValueError, match="CONSOLE_MODE"):
        BrowserController(console_mode="hologram")


def test_the_console_mode_defaults_to_the_setting(monkeypatch):
    monkeypatch.setattr(config, "CONSOLE_MODE", "overlay")
    assert BrowserController().console_mode == "overlay"
    monkeypatch.setattr(config, "CONSOLE_MODE", "browser")
    assert BrowserController().console_mode == "browser"
    assert BrowserController(console_mode="overlay").console_mode == "overlay"


async def test_overlay_mode_opens_only_the_agent_window():
    controller = BrowserController(console_mode="overlay", headless=True, mode="chromium")
    await controller.start()
    try:
        assert controller.console_page is None and controller.active is not None
        assert [t["index"] for t in await controller.list_tabs()] == [0]
        await controller.goto("data:text/html,<title>Agent page</title><h1>hello</h1>")
        assert (await controller.list_tabs())[0]["title"] == "Agent page"
        await controller.refocus_console()          # nothing to refocus in a headless run, and it must not raise
    finally:
        await controller.close()


async def test_browser_mode_still_opens_a_console_window():
    controller = BrowserController(console_mode="browser", headless=True, mode="chromium",
                                   console_url="data:text/html,<title>Console</title>")
    await controller.start()
    try:
        assert controller.console_page is not None and await controller.console_page.title() == "Console"
        assert len(await controller.list_tabs()) == 1       # the Console is not an agent tab
    finally:
        await controller.close()


def overlay_controller(headless=False):
    controller = BrowserController(console_mode="overlay", headless=headless, mode="chromium")
    controller.headless = headless
    return controller


async def test_refocus_brings_the_overlay_forward_by_its_title(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(browser_mod, "_win_force_foreground", lambda title: calls.append(title) or True)
    await overlay_controller().refocus_console()
    assert calls == [config.OVERLAY_TITLE] == ["PESU Assistant"]


async def test_refocus_retries_then_gives_up_quietly_when_there_is_no_overlay(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(browser_mod, "_win_force_foreground", lambda title: calls.append(title) or False)
    await overlay_controller().refocus_console()           # no overlay running: no exception, no crash
    assert calls == [config.OVERLAY_TITLE] * 3


async def test_refocus_does_nothing_headless_or_off_windows(monkeypatch):
    calls = []
    monkeypatch.setattr(browser_mod, "_win_force_foreground", lambda title: calls.append(title) or True)
    monkeypatch.setattr(sys, "platform", "win32")
    await overlay_controller(headless=True).refocus_console()
    monkeypatch.setattr(sys, "platform", "linux")
    await overlay_controller().refocus_console()
    assert calls == []
