"""BRW-03: perception.snapshot and main_text against every mock page, label fallbacks, caps and iframes."""
import functools
import http.server
import json
import os
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright  # noqa: E402

from app.perception import MAX_ELEMENTS, classify_button, locate, main_text, snapshot  # noqa: E402
from app.session import Session  # noqa: E402

MOCK_SITE = Path(__file__).resolve().parent.parent / "mock_site"
MOCK_PAGES = ["portal/index.html", "portal/apply.html", "portal/help.html", "portal/ack.html?ack=DPP-2026-1",
              "web/search.html?q=kalpana+chawla", "web/article.html", "web/shop.html", "web/cart.html",
              "web/checkout.html", "web/order.html?order=AS-1&total=10", "web/inbox.html", "web/message.html?id=4"]
FIELD_KEYS = {"id", "label", "type", "required", "value", "error", "sensitive_hint"}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def port():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(MOCK_SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


@pytest.fixture
def base(port):
    return f"http://127.0.0.1:{port}"


@pytest.fixture
async def page():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()
        yield await context.new_page()
        await browser.close()


def check_contract(snap: dict, session: Session) -> None:
    assert set(snap) == {"page_title", "url", "domain", "summary", "headings", "fields", "links", "tabs",
                         "buttons", "errors"}
    assert isinstance(snap["summary"], str) and "\n" not in snap["summary"]
    json.dumps(snap)  # plain JSON
    for f in snap["fields"]:
        assert FIELD_KEYS <= set(f) and len(f["label"]) < 60
    for b in snap["buttons"]:
        assert set(b) == {"id", "text", "irreversible", "kind"} and len(b["text"]) < 60
        assert b["kind"] in {"submit", "pay", "send", "post", "delete", "accept", "other"}
    for item in snap["links"] + snap["tabs"]:
        assert len(item["text"]) < 60
    ids = [x["id"] for k in ("fields", "buttons", "links", "tabs") for x in snap[k]]
    assert len(ids) == len(set(ids)) <= MAX_ELEMENTS
    assert set(ids) == set(session.locators)


@pytest.mark.parametrize("path", MOCK_PAGES)
async def test_every_mock_page_gives_contract_json(page, base, path):
    if path.startswith("web/checkout"):
        await page.goto(f"{base}/web/shop.html")
        await page.click("#add-cane")
    await page.goto(f"{base}/{path}")
    session = Session()
    snap = await snapshot(page, session)
    check_contract(snap, session)
    assert snap["domain"] == "127.0.0.1" and snap["page_title"]
    for element_id in session.locators:
        assert await locate(page, session, element_id).count() == 1, element_id


async def test_portal_form_fields_tabs_and_sensitive(page, base):
    await page.goto(f"{base}/portal/apply.html")
    session = Session()
    snap = await snapshot(page, session)
    labels = {f["label"]: f for f in snap["fields"]}
    assert {"Full name", "Date of birth", "PIN code", "Aadhaar number", "Category"} <= set(labels)
    assert labels["Aadhaar number"]["sensitive_hint"] and not labels["PIN code"]["sensitive_hint"]
    assert labels["Category"]["options"][:2] == ["Select a category", "General"]
    assert "Bank account number" not in labels  # hidden tab panel is not reported
    assert [(t["text"], t["selected"]) for t in snap["tabs"]] == [("Personal Details", True), ("Bank Details", False)]
    assert snap["headings"][0] == "Disability Pension Application"

    await locate(page, session, labels["Aadhaar number"]["id"]).fill("123412341234")
    await locate(page, session, labels["Full name"]["id"]).fill("Asha Kumari")
    snap = await snapshot(page, session)
    values = {f["label"]: f["value"] for f in snap["fields"]}
    assert values["Aadhaar number"] == "(filled)" and values["Full name"] == "Asha Kumari"
    assert "1234" not in json.dumps(snap)  # hard rule 4: no sensitive digits in the snapshot

    tab = next(t for t in snap["tabs"] if t["text"] == "Bank Details")
    await locate(page, session, tab["id"]).click()
    snap = await snapshot(page, session)
    bank = {f["label"]: f for f in snap["fields"]}
    assert bank["Bank account number"]["sensitive_hint"] and bank["IFSC code"]["sensitive_hint"]
    assert {b["text"]: b["kind"] for b in snap["buttons"]}["Submit application"] == "submit"


async def test_errors_after_invalid_submit(page, base):
    await page.goto(f"{base}/portal/apply.html")
    await page.click("#tab-bank")
    await page.click("#submit-application")
    snap = await snapshot(page, Session())
    name = next(f for f in snap["fields"] if f["label"] == "Full name")
    assert name["error"] == "Enter your full name."
    assert any("There is a problem" in e for e in snap["errors"])
    assert "with errors" in snap["summary"]


async def test_label_fallbacks(page):
    await page.set_content("""
      <span id=lbl>Labelled by span</span><input aria-labelledby=lbl>
      <input aria-label="Aria label">
      <input placeholder="Placeholder text">
      <div>Nearby text <input></div>
      <input name="by_name">
      <input id="by_id">
      <button aria-label="Close dialog">x</button>
      <a href="#"><img alt="Home icon"></a>
    """)
    snap = await snapshot(page, Session())
    assert [f["label"] for f in snap["fields"]] == ["Labelled by span", "Aria label", "Placeholder text",
                                                   "Nearby text", "by_name", "by_id"]
    assert snap["buttons"][0]["text"] == "Close dialog"
    assert snap["links"][0]["text"] == "Home icon"


async def test_caps_and_long_labels(page):
    links = "".join(f"<a href='#{i}'>Link number {i} with a very long title that goes well past the limit</a><br>"
                    for i in range(100))
    await page.set_content(f"<input aria-label='Name'>{links}")
    session = Session()
    snap = await snapshot(page, session)
    assert len(snap["fields"]) == 1  # fields are kept first when the cap is hit
    assert len(snap["fields"]) + len(snap["links"]) == MAX_ELEMENTS == len(session.locators)
    assert all(len(link["text"]) < 60 and link["text"].endswith("…") for link in snap["links"])


async def test_hidden_elements_are_skipped(page):
    await page.set_content("""<input aria-label=Shown><input aria-label=Gone style="display:none">
      <div hidden><button>Hidden</button></div><button style="visibility:hidden">Invisible</button>""")
    snap = await snapshot(page, Session())
    assert [f["label"] for f in snap["fields"]] == ["Shown"] and snap["buttons"] == []


async def test_new_snapshot_replaces_old_locators(page, base):
    session = Session()
    session.locators["custom"] = "#keep-me"
    await page.goto(f"{base}/web/article.html")
    await snapshot(page, session)
    await page.goto(f"{base}/portal/index.html")
    snap = await snapshot(page, session)
    ids = {x["id"] for k in ("fields", "buttons", "links", "tabs") for x in snap[k]}
    assert set(session.locators) == ids | {"custom"}


async def test_cross_origin_iframe(page, port):
    # The iframe is on localhost while the page is on 127.0.0.1: a different site (out-of-process frame).
    await page.goto(f"http://127.0.0.1:{port}/web/search.html")
    await page.evaluate("""src => { const f = document.createElement('iframe');
        f.src = src; f.style.width = '600px'; f.style.height = '400px'; document.body.appendChild(f); }""",
                        f"http://localhost:{port}/portal/apply.html")
    await page.wait_for_function("document.querySelector('iframe').contentWindow !== null")
    await page.wait_for_timeout(1000)
    session = Session()
    snap = await snapshot(page, session)
    full_name = next(f for f in snap["fields"] if f["label"] == "Full name")
    assert " >>> " in session.locators[full_name["id"]]
    await locate(page, session, full_name["id"]).fill("From the frame")
    frame = next(f for f in page.frames if "apply.html" in f.url)
    assert await frame.input_value("#full_name") == "From the frame"


async def test_main_text_strips_page_chrome(page, base):
    await page.goto(f"{base}/web/article.html")
    text = await main_text(page)
    assert text.startswith("Kalpana Chawla")
    assert "born on 17 March 1962 in Karnal" in text and "Born: 17 March 1962" in text
    for chrome in ("Random article", "Donate", "Related articles", "Sunita Williams", "Privacy policy", "cookies"):
        assert chrome not in text, chrome
    short = await main_text(page, max_chars=200)
    assert len(short) <= 201 and short.endswith("…")


async def test_main_text_reads_mail_body(page, base):
    await page.goto(f"{base}/web/message.html?id=4")
    text = await main_text(page)
    assert text.startswith("Dinner on Sunday?")
    assert "Are you free for dinner this Sunday at 7 pm?" in text
    assert "Reply" not in text and "Delete" not in text


async def test_main_text_on_form_page_is_not_empty(page, base):
    await page.goto(f"{base}/portal/apply.html")
    assert "Personal Details" in await main_text(page)


@pytest.mark.parametrize("text,btn_type,method,expected", [
    ("Submit application", "submit", "get", (True, "submit")),
    ("Place order", "submit", "get", (True, "pay")),
    ("Pay now", "button", None, (True, "pay")),
    ("Send", "submit", None, (True, "send")),
    ("Delete", "button", None, (True, "delete")),
    ("I agree", "button", None, (True, "accept")),
    ("Search", "submit", "get", (False, "other")),
    ("Save", "submit", "post", (True, "submit")),
    ("Add to cart", "button", None, (False, "other")),
    ("Reply", "button", None, (False, "other")),
    ("Next: Bank Details", "button", None, (False, "other")),
])
def test_classify_button(text, btn_type, method, expected):
    assert classify_button(text, btn_type, method) == expected


@pytest.mark.skipif(os.getenv("RUN_NETWORK_TESTS") != "1", reason="set RUN_NETWORK_TESTS=1 to hit Wikipedia")
async def test_real_wikipedia_article(page):
    await page.goto("https://en.wikipedia.org/wiki/Kalpana_Chawla", wait_until="domcontentloaded")
    session = Session()
    snap = await snapshot(page, session)
    check_contract(snap, session)
    assert snap["domain"] == "en.wikipedia.org" and snap["headings"][0] == "Kalpana Chawla"
    text = await main_text(page)
    assert text.startswith("Kalpana Chawla") and "Karnal" in text
    for chrome in ("Jump to content", "Create account", "View history", "64 languages"):
        assert chrome not in text, chrome
