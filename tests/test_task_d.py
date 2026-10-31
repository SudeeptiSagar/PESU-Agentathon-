"""BRW-07 step 3, Task D: open the inbox, open the newest message, read it (PRD 3.2).

The mock inbox and a stand-in Gmail page (served at mail.google.com through a route, offline) run
always. The real Gmail test needs the signed-in agent profile and runs only with RUN_REAL_GMAIL=1;
it checks structure only and never prints email text.
"""
import functools
import http.server
import os
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright  # noqa: E402

from app.humancheck import challenge_present  # noqa: E402
from app.perception import locate, main_text, snapshot  # noqa: E402
from app.session import Session  # noqa: E402

MOCK_SITE = Path(__file__).resolve().parent.parent / "mock_site"

GMAIL_INBOX = "<html><head><title>Inbox (3) - ramesh@example.com - Gmail</title></head><body>" + \
    "<div role=navigation><div role=button aria-label=Compose>Compose</div><a href='#inbox'>Inbox</a></div>" + \
    "<div role=main><table role=grid><tbody>" + "".join(
        f"<tr class=zA role=row><td><div role=checkbox aria-label='' aria-checked='false' "
        f"style='width:16px;height:16px;display:inline-block'></div></td>"
        f"<td><span role=button aria-label='Not starred'>&#9734;</span></td>"
        f"<td><div role=link tabindex=-1>Sender {i} - Subject number {i} - preview text of message {i}</div></td></tr>"
        for i in range(1, 51)) + "</tbody></table></div></body></html>"

# The thread is inserted 1.5 s after load, like Gmail rendering after "load".
GMAIL_MESSAGE = """<html><head><title>Lunch plan - Gmail</title></head><body>
<div role=navigation><div role=button aria-label=Compose>Compose</div><a href='#inbox'>Inbox</a><a href='#starred'>Starred</a></div>
<div role=main id=main></div>
<script>setTimeout(() => { document.getElementById('main').innerHTML = `
  <div role=button aria-label=Delete>Delete</div><div role=button aria-label=Reply>Reply</div>
  <h2 class=hP>Lunch plan</h2>
  <div role=list>
    <div role=listitem><span class=gD name="Asha" email="asha@example.com">Asha</span>
      <span class=g3 title="31 Oct 2026, 10:00">10:00</span><div class=a3s>First message: shall we meet at noon?</div></div>
    <div role=listitem><span class=gD name="Priya" email="priya@example.com">Priya</span>
      <span class=g3 title="31 Oct 2026, 11:30">11:30</span><div class=a3s>Newest message: yes, noon at the canteen works.</div></div>
  </div>`; }, 1500);</script></body></html>"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(MOCK_SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
async def page():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        yield await (await browser.new_context()).new_page()
        await browser.close()


async def test_mock_inbox_flow(page, base):
    await page.goto(f"{base}/web/inbox.html")
    session = Session()
    snap = await snapshot(page, session)
    assert await challenge_present(page) is None
    newest = next(link for link in snap["links"] if link["text"] == "Dinner on Sunday?")
    await locate(page, session, newest["id"]).click()
    await page.wait_for_url("**/message.html?id=4")
    text = await main_text(page)
    assert text.startswith("Dinner on Sunday?") and "dinner this Sunday at 7 pm" in text
    snap = await snapshot(page, Session())
    assert {b["text"]: b["kind"] for b in snap["buttons"] if b["irreversible"]} == {"Delete": "delete"}


async def fake_gmail(page, html):
    async def handle(route):
        await route.fulfill(body=html, content_type="text/html")
    await page.route("https://mail.google.com/**", handle)
    await page.goto("https://mail.google.com/mail/u/0/#inbox")


async def test_gmail_style_inbox_lists_rows_not_stars(page):
    await fake_gmail(page, GMAIL_INBOX)
    session = Session()
    snap = await snapshot(page, session)
    rows = [link for link in snap["links"] if link["text"].startswith("Sender")]
    assert rows[0]["text"].startswith("Sender 1 - Subject number 1")      # newest row is first
    assert len(rows) >= 20                                                # rows are not crowded out
    assert sum(b["text"] == "Not starred" for b in snap["buttons"]) == 2  # repeats listed twice at most
    toggles = [f for f in snap["fields"] if f["type"] == "checkbox"]
    assert all(f["value"] == "unchecked" for f in toggles)                # aria-checked is read
    assert all(len(link["text"]) < 60 for link in snap["links"])
    assert await challenge_present(page) is None                          # signed in: no hand-off


async def test_gmail_message_waits_and_reads_newest_first(page):
    await fake_gmail(page, GMAIL_MESSAGE)
    text = await main_text(page)                                          # waits for the late thread
    assert text.startswith("Lunch plan")
    newest, first = text.index("Newest message"), text.index("First message")
    assert newest < first                                                 # newest first
    assert "From: Priya <priya@example.com>" in text and "Date: 31 Oct 2026, 11:30" in text
    for ui in ("Compose", "Starred", "Delete", "Reply"):
        assert ui not in text, ui
    snap = await snapshot(page, Session())
    assert {b["text"]: b["kind"] for b in snap["buttons"] if b["irreversible"]} == {"Delete": "delete"}


async def test_google_sign_in_is_human_only(page):
    async def handle(route):
        await route.fulfill(body="<title>Sign in</title><input type=email aria-label='Email or phone'>",
                            content_type="text/html")
    await page.route("https://accounts.google.com/**", handle)
    await page.goto("https://accounts.google.com/v3/signin/identifier?continue=https://mail.google.com")
    assert (await challenge_present(page))["kind"] == "password"


@pytest.mark.skipif(os.getenv("RUN_REAL_GMAIL") != "1",
                    reason="set RUN_REAL_GMAIL=1 with a signed-in AGENT_PROFILE_DIR to read the real Gmail")
async def test_real_gmail_read_newest_message():
    from app.browser import BrowserController
    b = BrowserController(console_url="data:text/html,<title>Voice Console</title><textarea></textarea>",
                          mode="chrome")
    await b.start()
    try:
        page = b.active
        await b.goto("https://mail.google.com")
        session = Session()
        snap = await snapshot(page, session)
        assert await challenge_present(page) is None, "not signed in: sign in once in the agent Chrome"
        rows = [link["id"] for link in snap["links"]
                if await locate(page, session, link["id"]).evaluate("e => !!e.closest('tr.zA')")]
        assert rows, "no inbox rows found"
        await locate(page, session, rows[0]).click()
        text = await main_text(page)
        subject = await page.evaluate("() => (document.querySelector('h2.hP') || {}).innerText || ''")
        assert subject and text.startswith(subject.strip()) and "From: " in text
        assert await challenge_present(page) is None
    finally:
        await b.close()
