"""JEV-02 integration: the real mock portal's silent PIN-code truncation.

The unit tests in test_verifier.py use page.set_content. This test uses M3's real
portal, the real perception locators and the real 150 ms truncation, so it proves
the demo trap is caught in the same shape the agent will see.

It skips while app/verifier.py is still the CORE-01 stub.
"""
import functools
import http.server
import inspect
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright  # noqa: E402

from app import perception, verifier  # noqa: E402
from app.session import Session  # noqa: E402

MOCK_SITE = Path(__file__).resolve().parent.parent / "mock_site"

pytestmark = pytest.mark.skipif(
    "STUB:" in inspect.getsource(verifier.verify),
    reason="JEV-02 verifier is still the CORE-01 stub",
)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base():
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(MOCK_SITE))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
async def page():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()
        yield await context.new_page()
        await browser.close()


async def _open_portal(page, base):
    await page.goto(f"{base}/portal/apply.html")
    session = Session()
    snap = await perception.snapshot(page, session)
    fields = {field["label"]: field for field in snap["fields"]}
    return session, fields


@pytest.mark.asyncio
async def test_real_portal_truncated_pin_is_a_visible_mismatch(page, base):
    session, fields = await _open_portal(page, base)
    name = fields["Full name"]
    pin = fields["PIN code"]
    aadhaar = fields["Aadhaar number"]

    await perception.locate(page, session, name["id"]).fill("Ramesh Kumar")
    await perception.locate(page, session, pin["id"]).fill("560001")
    # The mock portal drops the last digit 150 ms after the sixth digit arrives.
    await page.wait_for_timeout(400)
    await perception.locate(page, session, aadhaar["id"]).fill("123456789012")

    session.expected = {
        name["id"]: {"label": "Full name", "selector": session.locators[name["id"]],
                     "value": "Ramesh Kumar", "type": "text", "source": "profile:full_name"},
        pin["id"]: {"label": "PIN code", "selector": session.locators[pin["id"]],
                    "value": "560001", "type": "text", "source": "profile:pin_code"},
        aadhaar["id"]: {"label": "Aadhaar number", "selector": session.locators[aadhaar["id"]],
                        "value": "123456789012", "type": "text", "source": "profile:aadhaar"},
    }

    problems = await verifier.verify(page, session)
    by_id = {problem["field_id"]: problem for problem in problems}

    assert pin["id"] in by_id, problems
    mismatch = by_id[pin["id"]]
    assert mismatch["kind"] == "mismatch"
    assert mismatch["expected"] == "560001"
    assert mismatch["actual"] == "56000"
    # pin_code is a postal code, not the unlock PIN: it must not be masked.
    assert "ending" not in mismatch["actual"]

    assert name["id"] not in by_id, problems
    assert aadhaar["id"] not in by_id, problems
    # Hard rule 4: the raw Aadhaar digits never appear in the verifier output.
    assert "123456789012" not in str(problems)
    assert "1234 5678 9012" not in str(problems)


@pytest.mark.asyncio
async def test_real_portal_required_field_never_filled_is_missing(page, base):
    session, fields = await _open_portal(page, base)
    # Fill only the PIN code; the required name stays empty and is not in expected.
    pin = fields["PIN code"]
    await perception.locate(page, session, pin["id"]).fill("560001")
    await page.wait_for_timeout(400)
    session.expected = {
        pin["id"]: {"label": "PIN code", "selector": session.locators[pin["id"]],
                    "value": "560001", "type": "text", "source": "profile:pin_code"},
    }

    problems = await verifier.verify(page, session)
    missing_labels = [problem["label"] for problem in problems if problem["kind"] == "missing"]
    assert any("Full name" in label for label in missing_labels), problems


STABLE = {
    "Full name": "#full_name",
    "Date of birth": "#dob",
    "Gender": "#gender",
    "Mobile number": "#phone",
    "Email address (optional)": "#email",
    "Address": "#address",
    "City": "#city",
    "State": "#state",
    "PIN code": "#pin_code",
    "Aadhaar number": "#aadhaar",
    "Annual family income (Rs)": "#annual_income",
    "Category": "#category",
    "Disability percentage": "#disability_percent",
    "Bank account number": "#bank_account",
    "IFSC code": "#ifsc",
}


def _exact(snap, label):
    if "fields" not in snap:
        return snap[label]
    return next(field for field in snap["fields"] if field["label"].lower() == label.lower())


def _record(field, value, source, stable):
    return {
        "label": field["label"],
        "selector": stable,
        "value": value,
        "type": field["type"],
        "source": source,
    }


@pytest.mark.asyncio
async def test_real_portal_full_form_reports_only_the_planted_pin_trap(page, base):
    session, snap = await _open_portal(page, base)
    expected = {}

    personal = {
        "Full name": "Ramesh Kumar",
        "Date of birth": "1980-03-04",
        "Mobile number": "9876543210",
        "Email address (optional)": "ramesh@example.com",
        "Address": "12 MG Road",
        "City": "Bengaluru",
        "State": "Karnataka",
        "PIN code": "560001",
        "Aadhaar number": "123456789012",
        "Annual family income (Rs)": "240000",
        "Disability percentage": "40",
    }
    for label, value in personal.items():
        field = _exact(snap, label)
        await perception.locate(page, session, field["id"]).fill(value)
        expected[field["id"]] = _record(field, value, f"profile:{label}", STABLE[label])

    for label, value in (("Gender", "Male"), ("Category", "General")):
        field = _exact(snap, label)
        await perception.locate(page, session, field["id"]).select_option(label=value)
        expected[field["id"]] = _record(field, value, f"profile:{label.lower()}", STABLE[label])

    # The portal drops the last digit 150 ms after the sixth digit arrives.
    await page.wait_for_timeout(400)

    await page.click("#tab-bank")
    snap_bank = await perception.snapshot(page, session)
    for label, value in (("Bank account number", "123456789012"),
                         ("IFSC code", "SBIN0001234")):
        field = _exact(snap_bank, label)
        await perception.locate(page, session, field["id"]).fill(value)
        expected[field["id"]] = _record(field, value, f"profile:{label}", STABLE[label])

    robot = next(
        field for field in snap_bank["fields"] if "not a robot" in field["label"].lower()
    )
    await perception.locate(page, session, robot["id"]).check()
    expected[robot["id"]] = _record(robot, "true", "profile:not_robot", "#not_robot")
    session.expected = expected

    problems = await verifier.verify(page, session)
    assert len(problems) == 1, problems
    assert problems[0]["label"] == "PIN code"
    assert problems[0]["kind"] == "mismatch"
    assert problems[0]["expected"] == "560001"
    assert problems[0]["actual"] == "56000"
    assert "123456789012" not in str(problems)

    # Correct it like the agent would, on the personal tab, then re-check.
    await page.click("#tab-personal")
    await page.fill("#pin_code", "560001")
    await page.wait_for_timeout(400)
    assert await verifier.verify(page, session) == []
