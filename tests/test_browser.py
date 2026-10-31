"""BRW-02: BrowserController tabs, new-tab announcement, navigation and Console focus (headless)."""
import asyncio
import http.server
import threading

import pytest

pytest.importorskip("playwright.async_api")

from app.browser import BrowserController  # noqa: E402

PAGES = {
    "/console": "<title>Voice Console</title><textarea id=box></textarea><button>x</button>",
    "/one": "<title>Page one</title><a id=popup href='/two' target='_blank'>open two</a>",
    "/two": "<title>Page two</title><p>second</p>",
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path)
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write((body or "not found").encode())

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
async def browser(site):
    announced = []
    b = BrowserController(on_new_tab=lambda title, url: announced.append((title, url)),
                          headless=True, console_url=f"{site}/console")
    b.announced = announced
    await b.start()
    yield b
    await b.close()


async def wait_for(condition, timeout=5.0):
    for _ in range(int(timeout / 0.05)):
        if condition():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition not met in time")


async def test_start_opens_console_and_one_agent_tab(browser, site):
    assert browser.console_page.url == f"{site}/console"
    tabs = await browser.list_tabs()
    assert len(tabs) == 1 and tabs[0]["active"] and tabs[0]["index"] == 0
    assert browser.active is not browser.console_page


async def test_goto_and_go_back(browser, site):
    await browser.goto(f"{site}/one")
    await browser.goto(f"{site}/two")
    await browser.go_back()
    assert browser.active.url == f"{site}/one"


async def test_new_tab_is_followed_and_announced(browser, site):
    await browser.goto(f"{site}/one")
    first = browser.active
    await first.click("#popup")
    await wait_for(lambda: browser.announced)
    assert browser.announced == [("Page two", f"{site}/two")]
    assert browser.active is not first and browser.active.url == f"{site}/two"
    tabs = await browser.list_tabs()
    assert [t["title"] for t in tabs] == ["Page one", "Page two"]
    assert [t["active"] for t in tabs] == [False, True]


async def test_switch_and_close_tabs(browser, site):
    await browser.goto(f"{site}/one")
    await browser.active.click("#popup")
    await wait_for(lambda: len(browser._pages) == 2)

    await browser.switch_tab(0)
    assert browser.active.url == f"{site}/one"

    await browser.close_tab(1)
    tabs = await browser.list_tabs()
    assert len(tabs) == 1 and tabs[0]["url"] == f"{site}/one" and tabs[0]["active"]

    await browser.close_tab(0)  # closing the last tab leaves a fresh blank one
    tabs = await browser.list_tabs()
    assert len(tabs) == 1 and tabs[0]["url"] == "about:blank" and browser.active is not None


async def test_closing_active_tab_activates_another(browser, site):
    await browser.goto(f"{site}/one")
    await browser.active.click("#popup")
    await wait_for(lambda: len(browser._pages) == 2)
    await browser.close_tab(1)
    assert browser.active.url == f"{site}/one"


async def test_bad_tab_index_raises(browser):
    with pytest.raises(IndexError):
        await browser.switch_tab(5)
    with pytest.raises(IndexError):
        await browser.close_tab(-1)


async def test_async_on_new_tab_callback(site):
    seen = []

    async def announce(title, url):
        seen.append(title)

    b = BrowserController(on_new_tab=announce, headless=True, console_url=f"{site}/console")
    await b.start()
    try:
        await b.goto(f"{site}/one")
        await b.active.click("#popup")
        await wait_for(lambda: seen)
        assert seen == ["Page two"]
    finally:
        await b.close()


async def test_refocus_console_focuses_text_box(browser, site):
    await browser.console_page.focus("button")
    await browser.goto(f"{site}/one")
    await browser.refocus_console()
    tag = await browser.console_page.evaluate("document.activeElement.tagName")
    assert tag == "TEXTAREA"


async def test_console_unreachable_still_starts():
    b = BrowserController(headless=True, console_url="http://127.0.0.1:9/console")
    await b.start()
    try:
        assert len(await b.list_tabs()) == 1
        await b.refocus_console()
    finally:
        await b.close()
