"""BRW-01: the mock disability pension portal behaves as the demo needs (headless Playwright)."""
import functools
import http.server
import threading
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

MOCK_SITE = Path(__file__).resolve().parent.parent / "mock_site"

VALID = {
    "full_name": "Asha Kumari",
    "dob": "1980-03-04",
    "phone": "9876543210",
    "address": "12 MG Road, Bengaluru",
    "pin_code": "560001",
    "aadhaar": "123412341234",
    "annual_income": "120000",
    "disability_percent": "60",
    "bank_account": "001234567890",
    "ifsc": "SBIN0001234",
}


@pytest.fixture(scope="module")
def base_url():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(MOCK_SITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/portal"
    server.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    yield context.new_page()
    context.close()


def fill_personal(page, pin_attempts=2):
    for key in ("full_name", "dob", "phone", "address", "aadhaar", "annual_income", "disability_percent"):
        page.fill(f"#{key}", VALID[key])
    page.select_option("#category", "OBC")
    for _ in range(pin_attempts):
        page.fill("#pin_code", VALID["pin_code"])
        page.wait_for_timeout(300)


def test_landing_has_apply_and_help_in_new_tab(page, base_url):
    page.goto(f"{base_url}/index.html")
    assert page.get_by_role("link", name="Apply for disability pension").get_attribute("href") == "apply.html"
    with page.context.expect_page() as new_tab:
        page.get_by_role("link", name="Read the help guide (opens in a new tab)").click()
    help_page = new_tab.value
    help_page.wait_for_load_state()
    assert help_page.title() == "Help: Disability Pension Application"


def test_pin_code_trap_drops_last_digit_once(page, base_url):
    page.goto(f"{base_url}/apply.html")
    page.fill("#pin_code", "560001")
    page.wait_for_timeout(300)
    assert page.input_value("#pin_code") == "56000"
    page.fill("#pin_code", "560001")
    page.wait_for_timeout(300)
    assert page.input_value("#pin_code") == "560001"


def test_aadhaar_is_displayed_grouped(page, base_url):
    page.goto(f"{base_url}/apply.html")
    page.fill("#aadhaar", "123412341234")
    assert page.input_value("#aadhaar") == "1234 1234 1234"


def test_empty_submit_shows_errors(page, base_url):
    page.goto(f"{base_url}/apply.html")
    page.click("#tab-bank")
    page.click("#submit-application")
    assert page.url.endswith("/apply.html")
    assert page.is_visible("#form-errors")
    assert page.get_attribute("#full_name", "aria-invalid") == "true"
    assert page.text_content("#pin_code-error") == "Enter a 6-digit PIN code."
    assert page.get_attribute("#tab-personal", "aria-selected") == "true"


def test_trapped_pin_blocks_submit(page, base_url):
    page.goto(f"{base_url}/apply.html")
    fill_personal(page, pin_attempts=1)
    page.click("#next-bank")
    page.fill("#bank_account", VALID["bank_account"])
    page.fill("#ifsc", VALID["ifsc"])
    page.check("#not_robot")
    page.click("#submit-application")
    assert page.url.endswith("/apply.html")
    assert page.get_attribute("#pin_code", "aria-invalid") == "true"


def test_robot_check_is_required(page, base_url):
    page.goto(f"{base_url}/apply.html")
    fill_personal(page)
    page.click("#next-bank")
    page.fill("#bank_account", VALID["bank_account"])
    page.fill("#ifsc", VALID["ifsc"])
    page.click("#submit-application")
    assert page.text_content("#not_robot-error") == "Tick \"I'm not a robot\" to continue."
    assert page.get_attribute("#human-check", "data-humancheck") == "captcha"


def test_full_application_reaches_acknowledgment(page, base_url):
    page.goto(f"{base_url}/apply.html")
    fill_personal(page)
    page.click("#next-bank")
    page.fill("#bank_account", VALID["bank_account"])
    page.fill("#ifsc", "sbin0001234")
    assert page.input_value("#ifsc") == "SBIN0001234"
    page.check("#not_robot")
    page.click("#submit-application")
    page.wait_for_url("**/ack.html?*")
    assert page.text_content("#ack-number").startswith("DPP-2026-")
    assert "123412341234" not in page.url and "001234567890" not in page.url
