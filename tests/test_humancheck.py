"""BRW-04: humancheck.challenge_present detects human-only steps, is silent elsewhere, and sees them go."""
import functools
import http.server
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright  # noqa: E402

from app.humancheck import challenge_present  # noqa: E402

MOCK_SITE = Path(__file__).resolve().parent.parent / "mock_site"
NORMAL_PAGES = ["portal/index.html", "portal/apply.html", "portal/help.html", "portal/ack.html?ack=DPP-2026-1",
                "web/search.html?q=kalpana+chawla", "web/article.html", "web/shop.html", "web/cart.html",
                "web/order.html?order=AS-1&total=10", "web/inbox.html", "web/message.html?id=4"]


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


async def kind(page):
    found = await challenge_present(page)
    if found:
        assert found["hint"].endswith("say done.")
    return found and found["kind"]


@pytest.mark.parametrize("path", NORMAL_PAGES)
async def test_silent_on_normal_pages(page, base, path):
    await page.goto(f"{base}/{path}")
    assert await kind(page) is None


async def test_fake_robot_check_and_its_removal(page, base):
    await page.goto(f"{base}/portal/apply.html")
    assert await kind(page) is None          # the check sits on the hidden Bank Details tab
    await page.click("#tab-bank")
    assert await kind(page) == "captcha"
    await page.check("#not_robot")           # the human ticks it
    assert await kind(page) is None


async def test_checkout_payment_until_card_is_filled(page, base):
    await page.goto(f"{base}/web/shop.html")
    await page.click("#add-book")
    await page.goto(f"{base}/web/checkout.html")
    assert await kind(page) == "payment"     # the CVV is type=password but this is not a login
    await page.fill("#card_number", "4111111111111111")
    await page.fill("#card_name", "Ramesh Kumar")
    await page.fill("#card_expiry", "12/29")
    assert await kind(page) == "payment"     # still one card field empty
    await page.fill("#card_cvv", "123")
    assert await kind(page) is None


async def test_login_then_otp_flow(page, base):
    await page.goto(f"{base}/web/login.html")
    assert await kind(page) == "password"
    await page.fill("#email", "ramesh@example.com")
    await page.fill("#password", "secret")
    assert await kind(page) == "password"    # a filled password is not "done": the user signs in
    await page.click("#sign-in")
    await page.wait_for_url("**/otp.html")
    assert await kind(page) == "otp"
    await page.fill("#otp", "123456")
    assert await kind(page) is None
    await page.click("#verify")
    await page.wait_for_url("**/inbox.html")
    assert await kind(page) is None


async def test_otp_by_name_without_autocomplete(page):
    await page.set_content('<label for=c>Enter OTP</label><input id=c name=otp_code>')
    assert await kind(page) == "otp"


async def test_card_security_code_is_not_an_otp(page):
    await page.set_content('<label for=s>Security code</label><input id=s autocomplete=cc-csc>')
    assert await kind(page) == "payment"


async def test_recaptcha_widget_until_token_set(page):
    await page.route("**/*", lambda route: route.fulfill(body="<html>widget</html>", content_type="text/html"))
    await page.goto("https://shop.example/checkout")
    await page.set_content("""<form><div class="g-recaptcha">
        <iframe src="https://www.google.com/recaptcha/api2/anchor?k=x" width=300 height=80></iframe>
        <textarea name="g-recaptcha-response" style="display:none"></textarea></div></form>""")
    assert await kind(page) == "captcha"
    await page.evaluate("document.querySelector('[name=g-recaptcha-response]').value = 'token'")
    assert await kind(page) is None


async def test_payment_provider_iframe(page):
    await page.route("**/*", lambda route: route.fulfill(body="<html>card</html>", content_type="text/html"))
    await page.goto("https://shop.example/pay")
    await page.set_content('<iframe src="https://js.stripe.com/v3/elements" width=300 height=80></iframe>')
    assert await kind(page) == "payment"


async def test_google_sign_in_page_by_domain(page):
    # The first Google sign-in step shows only an email box; the domain alone makes it human-only.
    await page.route("**/*", lambda route: route.fulfill(
        body="<html><title>Sign in</title><input type=email aria-label='Email or phone'></html>",
        content_type="text/html"))
    await page.goto("https://accounts.google.com/v3/signin/identifier")
    assert await kind(page) == "password"


async def test_captcha_reported_before_password(page):
    await page.set_content("""<div class=fake-captcha><input type=checkbox aria-label=robot></div>
        <input type=password aria-label=Password>""")
    assert await kind(page) == "captcha"
