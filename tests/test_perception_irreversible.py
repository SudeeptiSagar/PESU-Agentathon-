"""BRW-08: every button and submit input on every mock page gets the right `irreversible` and `kind`."""
import functools
import http.server
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright  # noqa: E402

from app.perception import classify_button, locate, snapshot  # noqa: E402
from app.session import Session  # noqa: E402

MOCK_SITE = Path(__file__).resolve().parent.parent / "mock_site"
OTHER = (False, "other")

# Expected flags for EVERY control on each mock page state, written from what the control does.
# A missing or extra control fails the test, so nothing irreversible can slip through unflagged.
EXPECTED = {
    "portal/index.html": {},
    "portal/apply.html": {"Next: Bank Details": OTHER},
    "portal/apply.html#bank": {"Back: Personal Details": OTHER, "Submit application": (True, "submit")},
    "portal/help.html": {},
    "portal/ack.html?ack=DPP-2026-1": {},
    "web/search.html?q=kalpana+chawla": {"Search": OTHER},
    # The "Donate" menu link leads to giving money, so it is held like a pay button.
    "web/article.html": {"OK": OTHER, "Donate": (True, "pay")},
    "web/shop.html": {f"Add {p} to cart": OTHER for p in
                      ("Folding white cane", "Talking wrist watch", "Talking calculator", "Braille story book")},
    "web/cart.html": {"Remove Folding white cane from cart": OTHER},
    "web/checkout.html": {"Place order": (True, "pay")},
    "web/order.html?order=AS-1&total=10": {},
    "web/inbox.html": {"Compose": OTHER},
    # Sign-in and code pages are human-only (humancheck); their form submits are still held.
    "web/login.html": {"Sign in": (True, "submit")},
    "web/otp.html": {"Verify": (True, "submit")},
    "web/message.html?id=4": {"Reply": OTHER, "Forward": OTHER, "Delete": (True, "delete")},
    "web/message.html?id=4#reply": {"Reply": OTHER, "Forward": OTHER, "Delete": (True, "delete"),
                                    "Send": (True, "send")},
}


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


async def open_state(page, base, state):
    path, _, step = state.partition("#")
    if path.startswith(("web/cart", "web/checkout")):
        await page.goto(f"{base}/web/shop.html")
        await page.click("#add-cane")
    await page.goto(f"{base}/{path}")
    if step == "bank":
        await page.click("#tab-bank")
    elif step == "reply":
        await page.click("#reply-btn")


@pytest.mark.parametrize("state", list(EXPECTED))
async def test_every_control_on_every_mock_page(page, base, state):
    await open_state(page, base, state)
    session = Session()
    snap = await snapshot(page, session)
    got = {b["text"]: (b["irreversible"], b["kind"]) for b in snap["buttons"]}
    assert got == EXPECTED[state]
    for b in snap["buttons"]:
        assert await locate(page, session, b["id"]).count() == 1


# Controls seen on real sites. (html, expected (irreversible, kind)); the control is the only one on the page.
TRICKY = [
    ('<form method=post><input type=submit value="Pay ₹249"></form>', (True, "pay")),
    ('<form method=post action="/profile"><button>Continue</button></form>', (True, "submit")),
    ('<form><button type=submit>Next</button><input name=first_name></form>', (True, "submit")),
    ('<form method=post><input type=image src="data:," alt="Go" width=20 height=20></form>', (True, "submit")),
    ('<div role=button aria-label="Delete" tabindex=0 style="width:20px;height:20px"></div>', (True, "delete")),
    ('<div role=button tabindex=0>Send</div>', (True, "send")),
    ('<span role=menuitem tabindex=0>Move to trash</span>', (True, "delete")),
    ('<button id="send-btn" aria-label="">&#10148;</button>', (True, "send")),
    ('<button data-action="delete-message">&#128465;</button>', (True, "delete")),
    ('<button class="btn place-order">Continue</button>', (True, "pay")),
    ('<a href="/order/place" role=button>Buy now</a>', (True, "pay")),
    ('<a href="/mail/delete?id=4">Delete this message</a>', (True, "delete")),
    ('<button>Submit payment</button>', (True, "pay")),
    ('<button>I agree to the terms</button>', (True, "accept")),
    ('<button>Publish</button>', (True, "post")),
    ('<button>Cancel order</button>', (True, "delete")),
    ('<button>जमा करें</button>', (True, "submit")),
    ('<button>भुगतान करें</button>', (True, "pay")),
    ('<form role=search><input name=q><button>Go</button></form>', OTHER),
    ('<form action="/search"><input name=query><button type=submit>Find</button></form>', OTHER),
    ('<form><input name=q><button>Search</button></form>', OTHER),
    ('<div id=cookie-banner><button>Accept all</button></div>', OTHER),
    ('<button type=button>Add to cart</button>', OTHER),
    ('<button type=button>Cancel</button>', OTHER),
    ('<button type=button>Next</button>', OTHER),
    ('<button type=button>Reply</button>', OTHER),
    ('<button type=button>Remove</button>', OTHER),
]


@pytest.mark.parametrize("html,expected", TRICKY)
async def test_tricky_controls(page, html, expected):
    await page.set_content(html)
    snap = await snapshot(page, Session())
    assert len(snap["buttons"]) == 1, snap["buttons"]
    b = snap["buttons"][0]
    assert (b["irreversible"], b["kind"]) == expected, b


@pytest.mark.parametrize("html", [
    # BRW-06, seen on socialjustice.gov.in: long notice links that merely mention "post" or "pay".
    '<a href="/notice/42">CORRIGENDUM (Date extended for applications for the post of Consultant)</a>',
    '<a href="/schemes/pms">Post Matric Scholarship for Scheduled Castes students</a>',
    '<a href="/7cpc">Seventh Central Pay Commission orders and notifications</a>',
    '<a href="apply.html">Apply for disability pension</a>',
    '<a href="/terms">I agree to these terms (read)</a>',
    '<a href="/payments">Payment options</a>',
    '<a href="checkout.html">Proceed to checkout</a>',
])
async def test_navigation_links_stay_links(page, html):
    await page.set_content(html)
    snap = await snapshot(page, Session())
    assert snap["buttons"] == [] and len(snap["links"]) == 1


def test_text_beats_hints_and_order_of_kinds():
    assert classify_button("Submit payment", "submit", "post") == (True, "pay")
    assert classify_button("Delete and send", "button") == (True, "delete")
    assert classify_button("", "button", hints="btn send-btn") == (True, "send")
    assert classify_button("Accept", "button", cookie_banner=True) == OTHER
    assert classify_button("Go", "submit", "get", search_form=True) == OTHER
    assert classify_button("Go", "submit", None) == OTHER   # a submit-type button outside any form
