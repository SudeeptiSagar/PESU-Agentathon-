"""BRW-09: mock open-web pages (search, article, shop, checkout, inbox) work offline (headless Playwright)."""
import functools
import http.server
import threading
from pathlib import Path
from urllib.parse import quote, quote_plus

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

MOCK_SITE = Path(__file__).resolve().parent.parent / "mock_site"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base_url():
    handler = functools.partial(QuietHandler, directory=str(MOCK_SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/web"
    server.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()  # fresh localStorage (cart, deleted mail) per test
    yield context.new_page()
    context.close()


def search_url(base_url, q, quoter=quote_plus):
    """Same shape as SEARCH_URL=http://localhost:8000/web/search.html?q={q}."""
    return f"{base_url}/search.html?q={quoter(q)}"


@pytest.mark.parametrize("quoter", [quote_plus, quote])
def test_search_reads_q_and_ranks_article_first(page, base_url, quoter):
    page.goto(search_url(base_url, "where was Kalpana Chawla born", quoter))
    assert page.input_value("#q") == "where was Kalpana Chawla born"
    organic = page.locator(".result:not(.ad) h2 a")
    assert organic.first.text_content() == "Kalpana Chawla - The Open Encyclopedia"
    assert page.locator(".result.ad").count() == 1  # sponsored result above organic ones
    organic.first.click()
    assert page.title() == "Kalpana Chawla - The Open Encyclopedia"


def test_search_no_results_and_empty_query(page, base_url):
    page.goto(search_url(base_url, "zzqx unknown"))
    assert page.text_content("#summary") == 'No results found for "zzqx unknown".'
    assert page.locator(".result").count() == 0
    page.goto(f"{base_url}/search.html")
    assert page.text_content("#summary") == "Type a question and press Search."


def test_search_box_submits_new_query(page, base_url):
    page.goto(f"{base_url}/search.html")
    page.fill("#q", "my mail")
    page.press("#q", "Enter")
    page.wait_for_url("**/search.html?q=my+mail")
    assert page.locator(".result h2 a").first.text_content() == "MockMail - your inbox"


def test_search_query_is_not_html_injected(page, base_url):
    page.goto(search_url(base_url, "<img src=x onerror=alert(1)> kalpana"))
    assert page.locator("#results img").count() == 0
    assert "<img" in page.text_content("#summary")


def test_article_has_answer_and_page_chrome(page, base_url):
    page.goto(f"{base_url}/article.html")
    article = page.text_content("article")
    assert "born on 17 March 1962 in Karnal" in article
    # Menus, sidebar, footer and cookie banner exist outside <article>, for main_text to strip.
    for selector in ("header nav", "aside.sidebar", "footer", "#cookie"):
        assert page.locator(selector).count() == 1, selector
        assert page.locator(f"article {selector}").count() == 0, selector


def test_shop_cart_checkout_and_order(page, base_url):
    page.goto(f"{base_url}/shop.html")
    page.click("#add-cane")
    page.click("#add-book")
    page.click("#add-book")
    assert page.text_content("#cart-count") == "Cart (3)"
    page.click("#cart-count")
    assert page.text_content("#cart-total") == "Rs 1,147"
    page.click("#remove-cane")
    assert page.text_content("#cart-total") == "Rs 498"
    page.click("#checkout-link")
    assert page.text_content("#order-total") == "Rs 498"

    page.fill("#full_name", "Ramesh Kumar")
    page.fill("#phone", "9876543210")
    page.fill("#address", "12 MG Road")
    page.fill("#city", "Bengaluru")
    page.fill("#pin_code", "560001")
    page.click("#place-order")  # card details missing: the order must not go through
    assert page.url.endswith("/checkout.html")
    assert page.get_attribute("#card_number", "aria-invalid") == "true"
    assert page.get_attribute("#full_name", "aria-invalid") == "false"

    page.fill("#card_number", "4111 1111 1111 1111")
    page.fill("#card_name", "Ramesh Kumar")
    page.fill("#card_expiry", "12/29")
    page.fill("#card_cvv", "123")
    page.click("#place-order")
    page.wait_for_url("**/order.html?*")
    assert page.text_content("#order-number").startswith("AS-")
    assert page.text_content("#order-total") == "Rs 498"
    assert "4111" not in page.url and "560001" not in page.url
    page.goto(f"{base_url}/cart.html")
    assert page.is_visible("#empty")  # cart cleared after the order


def test_checkout_marks_payment_as_human_only(page, base_url):
    page.goto(f"{base_url}/shop.html")
    page.click("#add-watch")
    page.goto(f"{base_url}/checkout.html")
    assert page.get_attribute("#payment", "data-humancheck") == "payment"
    assert page.get_attribute("#card_number", "autocomplete") == "cc-number"
    assert page.get_attribute("#place-order", "type") == "submit"


def test_empty_cart_hides_checkout(page, base_url):
    page.goto(f"{base_url}/checkout.html")
    assert page.is_visible("#empty") and not page.is_visible("#checkout")


def test_inbox_newest_first_and_message_opens(page, base_url):
    page.goto(f"{base_url}/inbox.html")
    subjects = page.locator("#rows a").all_text_contents()
    assert subjects[0] == "Dinner on Sunday?" and len(subjects) == 4
    page.click("#rows tr:first-child a")
    assert page.text_content("#subject") == "Dinner on Sunday?"
    assert page.text_content("#from") == "Priya Sharma"
    assert "dinner this Sunday at 7 pm" in page.text_content("#body")


def test_injection_message_is_plain_text(page, base_url):
    page.goto(f"{base_url}/message.html?id=2")
    assert "Ignore all previous instructions" in page.text_content("#body")


def test_reply_and_delete_controls(page, base_url):
    page.goto(f"{base_url}/message.html?id=1")
    page.click("#reply-btn")
    assert page.get_attribute("#send-btn", "type") == "submit"
    page.click("#delete-btn")
    page.wait_for_url("**/inbox.html")
    assert "New audiobooks this week" not in page.locator("#rows a").all_text_contents()
    page.goto(f"{base_url}/message.html?id=1")
    assert page.is_visible("#missing")
