"""The Console must keep working when the browser cannot draw its WebGL orb.

Handy pastes into the Console's input box. The orb is decoration, so whatever happens to it (no WebGL, software-only
WebGL, a crash while drawing) the input box, speech, keys and activity panel must stay alive. These tests open the page the
backend really serves (the committed client/console.html), so they also fail if client/ is changed without rebuilding it.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 0x9246 is UNMASKED_RENDERER_WEBGL. Headless Chromium here renders with SwiftShader (software), so each script below makes the
# browser CLAIM a graphics card, to test the code path a real laptop takes.
CLAIM_HARDWARE = """
(() => { const orig = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (t, ...a) {
    const gl = orig.call(this, t, ...a);
    if (gl && (t === 'webgl2' || t === 'webgl') && !gl.__patched) {
      const real = gl.getParameter.bind(gl);
      gl.getParameter = p => (p === 0x9246 ? 'NVIDIA GeForce RTX (test)' : real(p));
      gl.__patched = true; }
    return gl; }; })();
"""
# A browser that claims hardware WebGL to our check (the first request) but whose drawing request then fails:
# a crash while the orb draws.
LATE_FAIL = """
(() => { const orig = HTMLCanvasElement.prototype.getContext; let n = 0;
  HTMLCanvasElement.prototype.getContext = function (t, ...a) {
    if (t === 'webgl2' || t === 'webgl') {
      if (n++ >= 1) return null;
      const gl = orig.call(this, t, ...a);
      if (gl) { const real = gl.getParameter.bind(gl); gl.getParameter = p => (p === 0x9246 ? 'NVIDIA GeForce RTX (test)' : real(p)); }
      return gl; }
    return orig.call(this, t, ...a); }; })();
"""
# A browser whose WebGL reports a software renderer (a laptop without a usable GPU driver).
SOFTWARE_GL = """
(() => { const orig = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (t, ...a) {
    const gl = orig.call(this, t, ...a);
    if (gl && (t === 'webgl2' || t === 'webgl') && !gl.__patched) {
      const real = gl.getParameter.bind(gl);
      gl.getParameter = p => (p === 0x9246 ? 'Microsoft Basic Render Driver' : real(p));
      gl.__patched = true; }
    return gl; }; })();
"""


@pytest.fixture(scope="module")
def port(tmp_path_factory):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    env = dict(os.environ, PORT=str(free), HOST="127.0.0.1", BROWSER_HEADLESS="true",
               PROFILE_PATH=str(tmp_path_factory.mktemp("no_profile") / "profile.json"))
    server = subprocess.Popen([sys.executable, "-m", "app.main"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{free}/health", timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            pytest.fail("the backend did not start")
        yield free
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()


async def open_console(port, args=(), init_script=None, query=""):
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(args=list(args))
    page = await (await browser.new_context()).new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    if init_script:
        await page.add_init_script(init_script)
    await page.goto(f"http://127.0.0.1:{port}/console{query}")
    await page.wait_for_timeout(1500)
    return pw, browser, page, errors


async def state_of(page):
    return await page.evaluate("""() => ({
        input: !!document.querySelector('.capture-input'),
        focused: document.activeElement && document.activeElement.className === 'capture-input',
        plain: !!document.querySelector('.plain-orb'),
        canvas: !!document.querySelector('canvas'),
        roots: document.getElementById('root').children.length })""")


async def can_type(page) -> bool:
    await page.keyboard.type("hello")
    return await page.evaluate("document.querySelector('.capture-input').value") == "hello"


async def check(port, **kw):
    pw, browser, page, errors = await open_console(port, **kw)
    try:
        return await state_of(page), await can_type(page), errors
    finally:
        await browser.close()
        await pw.stop()


async def test_no_webgl_at_all_leaves_a_working_input_and_a_plain_circle(port):
    state, typed, errors = await check(port, args=["--disable-3d-apis", "--disable-gpu"])
    assert state["roots"] == 1 and state["input"] and state["focused"] and typed
    assert state["plain"] and not state["canvas"]
    assert errors == []


async def test_software_only_webgl_is_treated_as_no_webgl(port):
    state, typed, errors = await check(port, init_script=SOFTWARE_GL)
    assert state["input"] and state["focused"] and typed and errors == []
    assert state["plain"] and not state["canvas"]


async def test_an_orb_that_crashes_while_drawing_falls_back_and_keeps_the_input(port):
    state, typed, errors = await check(port, init_script=LATE_FAIL)
    assert state["input"] and state["focused"] and typed
    assert state["plain"] and not state["canvas"]
    assert errors == []                                    # the failure is caught, not a page error


async def test_a_hardware_renderer_gets_the_real_orb(port):
    state, typed, errors = await check(port, init_script=CLAIM_HARDWARE)
    assert state["canvas"] and not state["plain"] and state["input"] and state["focused"] and typed
    assert errors == []


async def test_the_url_switch_forces_the_orb_on_or_off(port):
    off = await check(port, query="?orb=off")
    assert off[0]["plain"] and not off[0]["canvas"] and off[1]
    on = await check(port, query="?orb=on")
    assert on[0]["canvas"] and not on[0]["plain"] and on[1] and on[2] == []


async def test_a_typed_sentence_still_reaches_the_backend_without_webgl(port):
    pw, browser, page, errors = await open_console(port, args=["--disable-3d-apis", "--disable-gpu"])
    try:
        await page.keyboard.type("help")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1200)
        await page.keyboard.press("Alt+i")
        await page.wait_for_timeout(400)
        assert "stop, pause, continue" in await page.inner_text("body")
    finally:
        await browser.close()
        await pw.stop()
