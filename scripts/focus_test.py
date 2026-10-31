"""Focus test for the UI-04 decision gate (PRD 8.3 and 8.5).

Opens the agent window and the Voice Console window, performs 5 clicks in the agent window on the
mock portal, calls refocus_console() after each, and reports whether the Console has focus.

Two checks per click:
  page focus: the Console document reports document.hasFocus() and its text box is focused.
  OS focus:   (Windows only) the foreground OS window is the Console window. This is the one
              Handy cares about, because Handy pastes into the OS-focused window.

Run from the repo root:  python scripts/focus_test.py [--console-url URL]
If the backend is not running, a stand-in Console page with one text box is used.
"""
import argparse
import asyncio
import functools
import http.server
import sys
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.browser import CONSOLE_URL, BrowserController  # noqa: E402

STAND_IN_CONSOLE = ("<!doctype html><title>Voice Console (stand-in)</title>"
                    "<h1>Voice Console (stand-in)</h1><textarea id=box rows=4 cols=40 autofocus></textarea>")
CLICKS = ["#tab-bank", "#tab-personal", "#full_name", "#pin_code", "#next-bank"]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def serve_mock_site() -> str:
    handler = functools.partial(QuietHandler, directory=str(ROOT / "mock_site"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


def reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except Exception:
        return False


def os_foreground_title() -> str | None:
    if sys.platform != "win32":
        return None
    import ctypes
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


async def main(console_url: str) -> int:
    site = serve_mock_site()
    if reachable(console_url):
        print(f"Console: {console_url}")
    else:
        print(f"Console: {console_url} not reachable, using the stand-in Console page")
        console_url = "data:text/html," + STAND_IN_CONSOLE

    browser = BrowserController(console_url=console_url)
    await browser.start()
    try:
        await browser.goto(f"{site}/portal/apply.html")
        console_title = await browser.console_page.title()
        passed = 0
        for n, selector in enumerate(CLICKS, 1):
            await browser.active.bring_to_front()
            await browser.active.click(selector)
            await asyncio.sleep(0.3)
            before = os_foreground_title()  # should be the agent window, proving focus moved away
            await browser.refocus_console()
            await asyncio.sleep(0.3)  # let the window manager settle
            page_focus = await browser.console_page.evaluate(
                "() => document.hasFocus() && ['TEXTAREA','INPUT'].includes(document.activeElement.tagName)")
            fg = os_foreground_title()
            os_focus = None if fg is None else console_title in fg
            ok = page_focus and os_focus is not False
            passed += ok
            os_text = "n/a (not Windows)" if fg is None else f"{os_focus} (after click: {before!r})"
            if os_focus is False:
                os_text += f" (in front instead: {fg!r})"
            print(f"Click {n} on {selector:<14} page focus: {page_focus}  OS focus: {os_text}  -> {'PASS' if ok else 'FAIL'}")
        print(f"Result: {passed}/{len(CLICKS)} clicks left the Console focused")
        return 0 if passed == len(CLICKS) else 1
    finally:
        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--console-url", default=CONSOLE_URL)
    sys.exit(asyncio.run(main(parser.parse_args().console_url)))
