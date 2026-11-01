"""Production Console accessibility regressions served by FastAPI."""
from __future__ import annotations

import socket
import threading
import time
import urllib.request
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, sync_playwright

from app import main


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "client"
RESPONSE = "This response is announced once."


@pytest.fixture(scope="module")
def production_pages():
    """The committed, already-built Console. Read-only: this test never runs npm and never writes into client/."""
    page = CLIENT / "console.html"
    if not page.exists():
        pytest.skip("client/console.html is not built")
    return {"browser": page}


@pytest.fixture(scope="module")
def chromium() -> Browser:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture(scope="module", params=("browser",))
def live_console(request, production_pages):
    """Serve the built page from the actual FastAPI /console and /ws/console routes."""
    old_tts_backend = main.config.TTS_BACKEND
    old_port = main.config.PORT
    old_handle = main.agent.handle_utterance
    old_stop = main.agent.stop
    page = production_pages[request.param]
    received = []
    stops = []

    async def handle_utterance(text, ctx):
        received.append(text)
        if text == "qa accessibility request":
            await ctx.emit("step", action="Click", target="Save", result="done")
            await ctx.emit(
                "field_table",
                fields=[{"label": "email", "value_masked": "v***@example.com", "status": "filled"}],
            )
            await ctx.emit("alert", level="error", message="A test alert")
            await ctx.say(RESPONSE)
        else:
            await ctx.say(f"You said: {text}")

    async def stop(ctx):
        stops.append(True)
        await ctx.say("Stopped.")

    main.config.TTS_BACKEND = "browser"
    main.agent.handle_utterance = handle_utterance
    main.agent.stop = stop

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    main.config.PORT = port
    server = uvicorn.Server(
        uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error", lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}/console"
    for _ in range(100):
        try:
            with urllib.request.urlopen(url, timeout=0.2) as response:
                assert response.status == 200
            break
        except Exception:
            if not thread.is_alive():
                raise RuntimeError("FastAPI server exited before /console became available")
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("FastAPI /console did not become available")

    yield {"url": url, "mode": request.param, "received": received, "stops": stops}

    server.should_exit = True
    thread.join(timeout=5)
    main.config.TTS_BACKEND = old_tts_backend
    main.config.PORT = old_port
    main.agent.handle_utterance = old_handle
    main.agent.stop = old_stop


@pytest.fixture
def page(chromium: Browser, live_console) -> Page:
    context = chromium.new_context(viewport={"width": 1200, "height": 900})
    context.add_init_script(
        """(() => {
          window.__ttsCalls = [];
          window.__ttsCancels = 0;
          Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
            cancel() { window.__ttsCancels += 1; },
            speak(utterance) { window.__ttsCalls.push(utterance.text); }
          }});
          window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
        })();"""
    )
    page = context.new_page()
    page.goto(live_console["url"], wait_until="domcontentloaded")
    page.wait_for_function(
        "document.querySelector('.orb-button')?.getAttribute('aria-label')?.includes('connected')"
    )
    page.wait_for_function("document.activeElement?.getAttribute('aria-label') === 'Task input'")
    yield page
    context.close()


def _wait_for(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.02)
    assert predicate(), "timed out waiting for the Console WebSocket event"


def test_keyboard_tabs_input_orb_activity_without_focus_trap(page, live_console):
    assert page.evaluate("document.activeElement.getAttribute('aria-label')") == "Task input"

    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.classList.contains('orb-button')")
    assert page.locator(".orb-button").evaluate("el => getComputedStyle(el).outlineStyle") == "solid"

    page.keyboard.press("Alt+I")
    assert page.locator("#activity-panel").is_visible()
    assert page.evaluate("document.activeElement.classList.contains('orb-button')")

    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "activity-panel"

    page.keyboard.press("Alt+T")
    assert page.evaluate("document.activeElement.getAttribute('aria-label')") == "Task input"
    assert page.locator("[aria-label='Task input']").is_visible()


def test_handys_input_is_visible_before_debounce_and_sends_after_900ms(page, live_console):
    field = page.get_by_role("textbox", name="Task input")
    field.fill("a harmless Handy transcript")
    assert field.is_visible()
    assert field.input_value() == "a harmless Handy transcript"
    assert float(field.evaluate("el => parseFloat(getComputedStyle(el).fontSize)")) >= 20
    page.wait_for_timeout(250)
    assert live_console["received"] == []

    _wait_for(lambda: live_console["received"] == ["a harmless Handy transcript"])


def test_speech_response_uses_exactly_one_announcement_channel(page, live_console):
    page.get_by_role("textbox", name="Task input").fill("qa accessibility request")
    log = page.locator('[role="log"][aria-label="Agent messages"]')
    page.wait_for_function(
        "response => document.querySelector('[role=log][aria-label=\"Agent messages\"]')?.textContent.includes(response)",
        arg=RESPONSE,
    )

    live_response_count = page.locator(
        '[aria-live]:not([aria-live="off"]), [role="alert"]'
    ).evaluate_all(
        "(els, response) => els.reduce((count, el) => count + (el.textContent.includes(response) ? 1 : 0), 0)",
        RESPONSE,
    )
    if live_console["mode"] == "browser":
        assert page.locator('[role="log"]').get_attribute("aria-live") == "off"
        assert page.evaluate("window.__ttsCalls") == [RESPONSE]
        assert live_response_count == 0
    else:
        assert page.locator('[role="log"]').get_attribute("aria-live") == "polite"
        assert page.evaluate("window.__ttsCalls") == []
        assert live_response_count == 1


def test_masked_fields_have_semantic_headers_labels_values_and_status(page, live_console):
    page.get_by_role("textbox", name="Task input").fill("qa accessibility request")
    table = page.get_by_role("table", name="Masked fields")
    table.wait_for()
    assert table.get_by_role("columnheader", name="Field").count() == 1
    assert table.get_by_role("columnheader", name="Masked value").count() == 1
    assert table.get_by_role("columnheader", name="Status").count() == 1
    row = table.get_by_role("row", name="email v***@example.com filled")
    assert row.get_by_role("rowheader", name="email").count() == 1
    assert row.get_by_role("cell", name="v***@example.com").count() == 1
    assert row.get_by_role("cell", name="filled").count() == 1


def test_escape_stops_from_another_control_without_stealing_focus(page, live_console):
    orb = page.get_by_role("button", name="PESU assistant", exact=False)
    orb.focus()
    page.keyboard.press("Escape")
    _wait_for(lambda: live_console["stops"] == [True])
    page.wait_for_function(
        "document.querySelector('[role=log][aria-label=\"Agent messages\"]')?.textContent.includes('Stopped.')"
    )
    assert page.evaluate("document.activeElement.classList.contains('orb-button')")


def test_forced_colors_focus_and_input_contrast(page, live_console):
    page.keyboard.press("Alt+T")
    metrics = page.locator("[aria-label='Task input']").evaluate(
        "el => ({ font: parseFloat(getComputedStyle(el).fontSize), color: getComputedStyle(el).color, background: getComputedStyle(el).backgroundColor })"
    )
    assert metrics["font"] >= 20

    def contrast(foreground, background):
        import re

        def luminance(css_color):
            values = [int(part) / 255 for part in re.findall(r"\d+", css_color)[:3]]
            linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in values]
            return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

        high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    assert contrast(metrics["color"], metrics["background"]) >= 4.5

    page.emulate_media(forced_colors="active")
    assert page.evaluate("matchMedia('(forced-colors: active)').matches")
    page.keyboard.press("Tab")
    assert page.locator(".orb-button").evaluate("el => getComputedStyle(el).outlineStyle") == "solid"
    page.keyboard.press("Alt+I")
    page.keyboard.press("Tab")
    assert page.locator("#activity-panel").evaluate("el => getComputedStyle(el).outlineStyle") == "solid"

