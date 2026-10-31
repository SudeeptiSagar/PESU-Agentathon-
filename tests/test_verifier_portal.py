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
