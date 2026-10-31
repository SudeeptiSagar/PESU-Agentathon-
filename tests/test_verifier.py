"""JEV-02: the DOM verifier against real Chromium pages (no network)."""
import json

import pytest
from playwright.async_api import async_playwright

from app.session import Session
from app.verifier import verify


@pytest.fixture
async def page():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        try:
            yield page
        finally:
            await browser.close()


def session_for(expected: dict | None = None, locators: dict | None = None) -> Session:
    session = Session()
    session.expected = expected or {}
    session.locators = locators or {}
    return session


async def test_truncated_pin_code_is_a_visible_mismatch(page):
    await page.set_content(
        '<label for="pin_code">PIN code</label>'
        '<input id="pin_code" name="pin_code" type="text">'
    )
    # The planted demo trap: a script silently cuts the last digit.
    await page.evaluate("document.getElementById('pin_code').value = '56000'")

    problems = await verify(page, session_for(
        {"f3": {"label": "PIN code", "selector": "#pin_code", "value": "560001",
                "type": "text", "source": "profile:pin_code"}},
        {"f3": "#pin_code"},
    ))

    assert problems == [{
        "field_id": "f3",
        "label": "PIN code",
        "expected": "560001",
        "actual": "56000",
        "kind": "mismatch",
    }]


async def test_empty_required_field_is_missing(page):
    await page.set_content(
        '<label for="email">Email</label>'
        '<input id="email" name="email" type="email" required>'
    )

    problems = await verify(page, session_for())

    assert problems == [{
        "field_id": "email",
        "label": "Email",
        "expected": "",
        "actual": "",
        "kind": "missing",
    }]


async def test_empty_required_radio_group_is_reported_once(page):
    await page.set_content(
        '<input type="radio" name="gender" value="M" required>'
        '<input type="radio" name="gender" value="F">'
    )

    problems = await verify(page, session_for())

    assert [(p["field_id"], p["kind"]) for p in problems] == [("gender", "missing")]


@pytest.mark.parametrize("shown", [
    "1980-03-04",
    "04/03/1980",
    "4-3-1980",
    "4 March 1980",
    "March 4, 1980",
    "4 Mar 1980",
])
async def test_date_formats_match(page, shown):
    await page.set_content(f'<input id="dob" type="text" value="{shown}">')

    problems = await verify(page, session_for({
        "f2": {"label": "Date of birth", "selector": "#dob", "value": "1980-03-04",
               "type": "date", "source": "profile:dob"},
    }))

    assert problems == []


async def test_phone_with_country_code_and_spaces_matches_ten_digits(page):
    await page.set_content('<input id="phone" type="tel" value="+91 98765 43210">')

    problems = await verify(page, session_for({
        "f4": {"label": "Phone", "selector": "#phone", "value": "9876543210",
               "type": "tel", "source": "profile:phone"},
    }))

    assert problems == []


async def test_aadhaar_grouping_matches_plain_and_never_leaks_digits(page):
    await page.set_content('<input id="aadhaar" type="text" value="1234 5678 9012">')

    problems = await verify(page, session_for({
        "f5": {"label": "Aadhaar number", "selector": "#aadhaar",
               "value": "123456789012", "type": "text",
               "source": "profile:aadhaar"},
    }))

    assert problems == []
    assert "123456789012" not in json.dumps(problems)


async def test_sensitive_mismatch_is_masked_to_last_four(page):
    await page.set_content('<input id="aadhaar" type="text" value="1234 5678 9013">')

    problems = await verify(page, session_for({
        "f5": {"label": "Aadhaar number", "selector": "#aadhaar",
               "value": "123456789012", "type": "text",
               "source": "profile:aadhaar"},
    }))

    assert len(problems) == 1
    assert problems[0]["kind"] == "mismatch"
    assert problems[0]["expected"] == "ending 9 0 1 2"
    assert problems[0]["actual"] == "ending 9 0 1 3"
    assert "123456789012" not in json.dumps(problems)
    assert "123456789013" not in json.dumps(problems)


async def test_select_option_text_and_checkbox_checked(page):
    await page.set_content(
        '<label for="gender">Gender</label>'
        '<select id="gender">'
        '<option value="">Choose</option>'
        '<option value="M" selected>Male</option>'
        '</select>'
        '<label><input type="checkbox" id="terms" checked> I agree</label>'
    )
    expected = {
        "f6": {"label": "Gender", "selector": "#gender", "value": "Male",
               "type": "select", "source": "profile:gender"},
        "f7": {"label": "I agree", "selector": "#terms", "value": "yes",
               "type": "checkbox", "source": ""},
    }

    assert await verify(page, session_for(expected)) == []

    # The option's value attribute is accepted as a fallback for its text.
    expected["f6"]["value"] = "M"
    assert await verify(page, session_for(expected)) == []


async def test_name_case_and_whitespace_and_trailing_period(page):
    await page.set_content('<input id="full_name" type="text" value="  abishek   rao ">')

    problems = await verify(page, session_for({
        "f1": {"label": "Full name", "selector": "#full_name", "value": "Abishek Rao.",
               "type": "text", "source": "profile:full_name"},
    }))

    assert problems == []


async def test_ifsc_and_bank_account_normalisation(page):
    await page.set_content(
        '<input id="ifsc" type="text" value=" hdfc0 001234 ">'
        '<input id="account" type="text" value="1234-5678-9012">'
    )

    problems = await verify(page, session_for({
        "f10": {"label": "IFSC code", "selector": "#ifsc", "value": "HDFC0001234",
                "type": "text", "source": "profile:ifsc"},
        "f11": {"label": "Bank account number", "selector": "#account",
                "value": "1234 5678 9012", "type": "text",
                "source": "profile:bank_account"},
    }))

    assert problems == []


async def test_contenteditable_and_number_normalisation(page):
    await page.set_content(
        '<div id="bio" contenteditable="true">  Hello   world.  </div>'
        '<input id="income" type="text" value="Rs. 1,23,456.00">'
    )

    problems = await verify(page, session_for({
        "f12": {"label": "Bio", "selector": "#bio", "value": "hello world",
                "type": "contenteditable", "source": ""},
        "f13": {"label": "Annual income", "selector": "#income", "value": "123456",
                "type": "number", "source": "profile:annual_income"},
    }))

    assert problems == []


async def test_visible_field_error_is_reported(page):
    await page.set_content(
        '<div class="form-group">'
        '<label for="phone">Phone</label>'
        '<input id="phone" type="text" value="12345">'
        '<div class="field-error">Enter a valid 10-digit phone number</div>'
        '</div>'
    )

    problems = await verify(page, session_for({
        "f4": {"label": "Phone", "selector": "#phone", "value": "12345",
               "type": "tel", "source": "profile:phone"},
    }))

    assert problems == [{
        "field_id": "f4",
        "label": "Phone",
        "expected": "12345",
        "actual": "Enter a valid 10-digit phone number",
        "kind": "error",
    }]


async def test_browser_validation_message_is_reported(page):
    await page.set_content('<input id="email" type="email" value="not-an-email">')
    await page.evaluate(
        "document.getElementById('email').setCustomValidity('Use a valid email address')"
    )

    problems = await verify(page, session_for())

    assert [(p["field_id"], p["kind"]) for p in problems] == [("email", "error")]
    assert problems[0]["actual"] == "Use a valid email address"


async def test_sensitive_error_message_never_leaks_digits(page):
    await page.set_content(
        '<div class="form-group">'
        '<label for="aadhaar">Aadhaar number</label>'
        '<input id="aadhaar" type="text" value="1111 2222 3333">'
        '<div class="error">Aadhaar 1111 2222 3333 is invalid</div>'
        '</div>'
    )

    problems = await verify(page, session_for({
        "f5": {"label": "Aadhaar number", "selector": "#aadhaar", "value": "",
               "type": "text", "source": "profile:aadhaar"},
    }))

    assert [(p["field_id"], p["kind"]) for p in problems] == [("f5", "error")]
    assert "1111 2222 3333" not in json.dumps(problems)
    assert "111122223333" not in json.dumps(problems)


async def test_multiple_error_indicators_report_one_error(page):
    await page.set_content(
        '<div class="form-group">'
        '<label for="phone">Phone</label>'
        '<input id="phone" type="text" value="12345" aria-invalid="true" '
        'aria-describedby="phone-error">'
        '<div id="phone-error" class="field-error">Enter a valid phone number</div>'
        '</div>'
    )

    problems = await verify(page, session_for({
        "f4": {"label": "Phone", "selector": "#phone", "value": "12345",
               "type": "tel", "source": "profile:phone"},
    }))

    assert len(problems) == 1
    assert problems[0]["kind"] == "error"
    assert problems[0]["actual"] == "Enter a valid phone number"


async def test_hidden_and_disabled_required_fields_are_skipped(page):
    await page.set_content(
        '<input id="gone" name="gone" required style="display: none">'
        '<input id="off" name="off" required disabled>'
        '<textarea id="notes" name="notes" required></textarea>'
    )

    problems = await verify(page, session_for())

    assert problems == [{
        "field_id": "notes",
        "label": "notes",
        "expected": "",
        "actual": "",
        "kind": "missing",
    }]


async def test_unchecked_checkbox_matches_falsy_expected(page):
    await page.set_content('<input type="checkbox" id="terms">')

    problems = await verify(page, session_for({
        "f7": {"label": "I agree", "selector": "#terms", "value": "no",
               "type": "checkbox", "source": ""},
    }))

    assert problems == []


async def test_aria_describedby_error_text_is_reported(page):
    await page.set_content(
        '<label for="email">Email</label>'
        '<input id="email" type="text" aria-describedby="email-error">'
        '<span id="email-error">This field is required</span>'
    )

    problems = await verify(page, session_for())

    assert [(p["field_id"], p["kind"]) for p in problems] == [("email", "error")]
    assert problems[0]["actual"] == "This field is required"


async def test_iframe_locator_is_read(page):
    await page.set_content(
        "<iframe srcdoc='<input id=\"dob\" type=\"text\" value=\"04/03/1980\">'></iframe>"
    )

    problems = await verify(page, session_for({
        "f2": {"label": "Date of birth", "selector": "iframe >>> #dob",
               "value": "1980-03-04", "type": "date", "source": "profile:dob"},
    }, {"f2": "iframe >>> #dob"}))

    assert problems == []


async def test_missing_element_returns_a_missing_record_not_an_exception(page):
    await page.set_content("<p>No form here.</p>")

    problems = await verify(page, session_for({
        "f1": {"label": "City", "selector": "#city", "value": "Pune",
               "type": "text", "source": "profile:city"},
    }, {"f1": "#city"}))

    assert problems == [{
        "field_id": "f1",
        "label": "City",
        "expected": "Pune",
        "actual": "",
        "kind": "missing",
    }]
