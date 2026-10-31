"""JEV-07 safety chain: real Playwright page checks plus verifier, gate, readback and audit.

These tests run now. Parts that need a module which is still a CORE-01 stub skip with
the module and ticket named; they never pass on stub behaviour. The fixture checks and
the Console transport check run immediately.
"""
from __future__ import annotations

import json
import re

import httpx
import pytest
import pytest_asyncio

from tests.e2e import harness
from tests.e2e.harness import (
    CONFIRM_INSTRUCTION,
    FIXTURES,
    PROFILE,
    actual_values,
    app_server,
    assert_no_sensitive_text,
    assert_readback_safe,
    console_client,
    digits,
    fixture_site,
    make_portal_session,
    make_shop_session,
    stub_skip_reason,
)

PORTAL_HTML = (FIXTURES / "portal.html").read_text(encoding="utf-8")
SHOP_HTML = (FIXTURES / "shop.html").read_text(encoding="utf-8")

pytestmark = pytest.mark.e2e


@pytest_asyncio.fixture
async def page():
    """A real Chromium page, or a clear skip when the browser is not installed."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("playwright is not installed; run pip install -r requirements.txt")
    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.launch(headless=True)
    except Exception as exc:  # noqa: BLE001 - missing browser is a setup skip
        await playwright.stop()
        pytest.skip(f"Playwright Chromium is unavailable: {exc}. "
                    "Run: python -m playwright install chromium")
    page = await browser.new_page()
    try:
        yield page
    finally:
        await browser.close()
        await playwright.stop()


async def _load_portal(page) -> None:
    await page.set_content(PORTAL_HTML, wait_until="domcontentloaded")


async def _fill_portal(page, pin: str = PROFILE["pin_code"]) -> None:
    await page.fill("#full_name", PROFILE["full_name"])
    await page.fill("#dob", PROFILE["dob"])
    await page.fill("#pin_code", pin)
    await page.fill("#aadhaar", PROFILE["aadhaar"])


def test_stub_detector_sees_the_marker() -> None:
    """The skip mechanism itself must not silently pass on a stub."""

    def _stub_probe():
        # STUB: JEV-07 detector probe
        return None

    def _real_probe():
        return None

    assert harness.source_contains_stub(_stub_probe)
    assert not harness.source_contains_stub(_real_probe)


def _bare_client(events: list[harness.Event]) -> harness.ConsoleClient:
    client = harness.ConsoleClient.__new__(harness.ConsoleClient)
    client.events = events
    client._error = None
    return client


def test_event_guard_rejects_a_click_before_confirm() -> None:
    """The no-irreversible-before-confirm guard itself must fail closed."""
    client = _bare_client([
        harness.Event(1, "in", {"type": "pending", "description": "Submit application"}),
        harness.Event(2, "in", {"type": "step", "n": 1, "action": "click",
                                "target": "Submit application", "result": "clicked"}),
        harness.Event(3, "out", {"type": "utterance", "text": "confirm"}),
    ])
    with pytest.raises(AssertionError, match="irreversible control ran before confirm"):
        client.assert_no_irreversible_before_confirm(("submit",))


def test_event_guard_accepts_a_held_action() -> None:
    client = _bare_client([
        harness.Event(1, "in", {"type": "pending", "description": "Submit application"}),
        harness.Event(2, "in", {"type": "step", "n": 1, "action": "click",
                                "target": "Submit application",
                                "result": "held for confirmation"}),
        harness.Event(3, "out", {"type": "utterance", "text": "confirm"}),
    ])
    client.assert_no_irreversible_before_confirm(("submit",))


def test_event_guard_rejects_raw_aadhaar() -> None:
    client = _bare_client([
        harness.Event(1, "in", {"type": "speak", "text": f"Aadhaar {PROFILE['aadhaar']}"}),
    ])
    with pytest.raises(AssertionError, match="raw aadhaar appeared"):
        client.assert_no_sensitive_events()


@pytest.mark.asyncio
async def test_fixture_site_serves_self_contained_pages() -> None:
    with fixture_site() as site:
        async with httpx.AsyncClient(timeout=5.0) as http:
            search = await http.get(site.url("search.html"), params={"q": "kalpana"})
            article = await http.get(site.url("article.html"))
            portal = await http.get(site.url("portal.html"))
            shop = await http.get(site.url("shop.html"))
            inbox = await http.get(site.url("inbox.html"))
            message = await http.get(site.url("message.html"))
        assert search.status_code == 200
        assert "Kalpana Chawla - Wikipedia" in search.text
        assert article.status_code == 200 and "born in Karnal" in article.text
        assert portal.status_code == 200 and 'id="pin_code"' in portal.text
        assert shop.status_code == 200 and "Place order" in shop.text
        assert inbox.status_code == 200 and "Appointment confirmed" in inbox.text
        assert message.status_code == 200 and "untrusted data" in message.text


@pytest.mark.asyncio
async def test_console_transport_accepts_a_connection() -> None:
    """Harness self-check: uvicorn starts on a random port and /ws/console connects."""
    async with app_server() as server:
        async with console_client(server) as client:
            event = await client.wait_for(
                lambda item: item.direction == "in" and item.type == "state",
                "first state event", timeout=15,
            )
            assert event.data.get("name")


@pytest.mark.asyncio
async def test_fixture_portal_truncates_pin_once(page) -> None:
    """Real Playwright page.set_content: the planted trap drops one digit, once."""
    await _load_portal(page)
    await page.fill("#pin_code", PROFILE["pin_code"])
    assert await page.input_value("#pin_code") == PROFILE["pin_code"][:-1]
    assert await page.get_attribute("#pin_code", "data-truncated") == "true"

    await page.fill("#pin_code", PROFILE["pin_code"])
    assert await page.input_value("#pin_code") == PROFILE["pin_code"]

    assert await page.is_visible("#robot-check")
    assert not await page.is_checked("#robot")


@pytest.mark.asyncio
async def test_fixture_portal_human_mark_clears_the_check(page) -> None:
    with fixture_site() as site:
        await page.goto(site.url("portal.html"))
        assert await page.is_visible("#robot-check")
        site.mark_human_done()
        await page.wait_for_selector("#robot-check", state="detached", timeout=5000)
        assert await page.evaluate("document.body.dataset.humanCheck") == "done"


@pytest.mark.asyncio
async def test_fixture_portal_counts_one_submit_after_human_done(page) -> None:
    with fixture_site() as site:
        await page.goto(site.url("portal.html"))
        site.mark_human_done()
        await page.wait_for_selector("#robot-check", state="detached", timeout=5000)
        await page.click("#submit")
        await page.wait_for_function(
            "document.getElementById('status').textContent.includes('ACK-2026-0042')"
        )
        await site.wait_for_portal_submission(timeout=5)
        assert site.portal_attempts == 1
        assert site.portal_submissions == 1


@pytest.mark.asyncio
async def test_fixture_shop_defers_payment_until_order(page) -> None:
    await page.set_content(SHOP_HTML, wait_until="domcontentloaded")
    assert await page.is_hidden("#payment")
    assert await page.locator("#card_number").count() == 0

    await page.click("#add-to-cart")
    assert await page.inner_text("#total") == "249"
    await page.click("#place-order")
    assert await page.is_visible("#payment")
    assert await page.is_visible("#card_number")
    assert await page.get_attribute("#payment", "data-human-check") == "payment"


@pytest.mark.asyncio
async def test_verifier_catches_truncated_pin(page) -> None:
    reason = stub_skip_reason("verifier.verify")
    if reason:
        pytest.skip(reason)
    from app.verifier import verify

    await _load_portal(page)
    await _fill_portal(page)
    session = make_portal_session()

    problems = await verify(page, session)
    assert isinstance(problems, list), f"verify returned {type(problems)!r}"

    pin_problems = [
        problem for problem in problems
        if problem.get("field_id") == "f3"
        or "pin" in str(problem.get("label", "")).casefold()
    ]
    assert pin_problems, f"verifier missed the truncated PIN code: {harness.redact(repr(problems))}"
    problem = pin_problems[0]
    assert problem.get("kind") == "mismatch", harness.redact(repr(problem))
    assert digits(problem.get("expected")) == PROFILE["pin_code"], harness.redact(repr(problem))
    assert digits(problem.get("actual")) == PROFILE["pin_code"][:-1], harness.redact(repr(problem))

    assert not any("name" in str(item.get("label", "")).casefold() for item in problems), (
        f"verifier reported a false problem on the full name: "
        f"{harness.redact(repr(problems))}"
    )


@pytest.mark.asyncio
async def test_verifier_catches_missing_required_field(page) -> None:
    reason = stub_skip_reason("verifier.verify")
    if reason:
        pytest.skip(reason)
    from app.verifier import verify

    await _load_portal(page)
    await _fill_portal(page)
    await page.fill("#dob", "")
    session = make_portal_session()

    problems = await verify(page, session)
    dob_problems = [
        problem for problem in problems
        if problem.get("field_id") == "f2"
        or "birth" in str(problem.get("label", "")).casefold()
    ]
    assert dob_problems, f"verifier missed the empty date of birth: {harness.redact(repr(problems))}"
    assert any(problem.get("kind") == "missing" for problem in dob_problems), (
        harness.redact(repr(dob_problems))
    )


def _gate_context(domain: str, approved: set[str], element: dict | None = None) -> dict:
    return {
        "goal": "Apply for the disability pension on the demo portal.",
        "domain": domain,
        "approved_domains": approved,
        "element": element or {},
        "history_tail": [],
    }


@pytest.mark.asyncio
async def test_gate_never_proceeds_on_irreversible() -> None:
    reason = stub_skip_reason("gate.check")
    if reason:
        pytest.skip(reason)
    from app.gate import check

    element = {"id": "b1", "text": "Submit application", "irreversible": True,
               "kind": "submit"}
    result = await check(
        {"name": "click", "args": {"element_id": "b1"}},
        _gate_context("127.0.0.1", {"127.0.0.1"}, element),
    )
    assert result["decision"] in {"ask_user", "block"}, result
    assert result["decision"] != "proceed", result


@pytest.mark.asyncio
async def test_gate_blocks_blocked_domain(monkeypatch) -> None:
    reason = stub_skip_reason("gate.check")
    if reason:
        pytest.skip(reason)
    from app import config
    from app import gate as gate_module
    from app import tools as tools_module
    from app.gate import check

    monkeypatch.setattr(config, "BLOCKED_DOMAINS", {"blocked.example"})
    for module in (gate_module, tools_module):
        if hasattr(module, "BLOCKED_DOMAINS"):
            monkeypatch.setattr(module, "BLOCKED_DOMAINS", {"blocked.example"})

    result = await check(
        {"name": "navigate", "args": {"target": "http://blocked.example/"}},
        _gate_context("blocked.example", set()),
    )
    assert result["decision"] == "block", result


@pytest.mark.asyncio
async def test_gate_blocks_profile_fill_on_unapproved_domain() -> None:
    reason = stub_skip_reason("gate.check")
    if reason:
        pytest.skip(reason)
    from app.gate import check

    element = {"id": "f4", "label": "Aadhaar number", "sensitive_hint": True}
    result = await check(
        {"name": "fill_field", "args": {"field_id": "f4", "value_ref": "{aadhaar}"}},
        _gate_context("new.example", set(), element),
    )
    assert result["decision"] == "block", result


@pytest.mark.asyncio
async def test_gate_asks_on_first_sensitive_fill() -> None:
    reason = stub_skip_reason("gate.check")
    if reason:
        pytest.skip(reason)
    from app.gate import check

    element = {"id": "f4", "label": "Aadhaar number", "sensitive_hint": True}
    result = await check(
        {"name": "fill_field", "args": {"field_id": "f4", "value_ref": "{aadhaar}"}},
        _gate_context("127.0.0.1", {"127.0.0.1"}, element),
    )
    assert result["decision"] == "ask_user", result


@pytest.mark.asyncio
async def test_readback_masks_aadhaar_and_keeps_pin_code() -> None:
    reason = stub_skip_reason("readback.build_readback", "readback.describe_pending")
    if reason:
        pytest.skip(reason)
    from app.readback import build_readback

    session = make_portal_session()
    chunks = build_readback(session, actual_values(session))
    assert_readback_safe(chunks)
    joined = "\n".join(chunks)
    assert CONFIRM_INSTRUCTION in joined
    assert_no_sensitive_text(joined, "read-back")


@pytest.mark.asyncio
async def test_readback_uses_actual_page_values() -> None:
    reason = stub_skip_reason("readback.build_readback")
    if reason:
        pytest.skip(reason)
    from app.readback import build_readback

    session = make_portal_session()
    values = actual_values(session)
    values["f1"] = "Ramesh Kumaar"
    values["Full name"] = "Ramesh Kumaar"
    chunks = build_readback(session, values)
    joined = "\n".join(chunks)
    assert "Kumaar" in joined, (
        f"read-back did not use the actual value: {harness.redact(repr(chunks))}"
    )


@pytest.mark.asyncio
async def test_describe_pending_names_action_site_and_total() -> None:
    reason = stub_skip_reason("readback.describe_pending")
    if reason:
        pytest.skip(reason)
    from app.readback import describe_pending

    text = describe_pending(make_shop_session())
    lowered = text.casefold()
    assert "place order" in lowered, text
    assert "249" in re.sub(r"\D", "", text), text
    assert "shop" in lowered or "127.0.0.1" in lowered, text


def test_audit_drops_raw_sensitive_values(tmp_path, monkeypatch) -> None:
    reason = stub_skip_reason("audit.log_event")
    if reason:
        pytest.skip(reason)
    from app import audit, config

    target = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AUDIT_LOG_PATH", str(target))
    for module, attr in (
        (audit, "AUDIT_PATH"), (audit, "AUDIT_LOG_PATH"), (audit, "LOG_PATH"),
        (config, "AUDIT_PATH"), (config, "AUDIT_LOG_PATH"),
    ):
        if hasattr(module, attr):
            monkeypatch.setattr(module, attr, target)

    audit.log_event(
        "e2e_test",
        aadhaar=PROFILE["aadhaar"],
        bank_account=PROFILE["bank_account"],
        ifsc=PROFILE["ifsc"],
        pin_code=PROFILE["pin_code"],
        pin="9157",
        note="safe",
    )
    assert target.exists(), (
        f"audit.log_event wrote no file at {target}. JEV-06 must honour AUDIT_LOG_PATH "
        "or expose AUDIT_PATH/AUDIT_LOG_PATH."
    )
    text = target.read_text(encoding="utf-8")
    assert text.strip(), "audit log is empty"
    assert_no_sensitive_text(text, "audit log")
    assert "9157" not in text, "the app PIN must never be written to the audit log"
    assert PROFILE["pin_code"] in text, "non-sensitive PIN code should remain in the audit log"

    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    assert any(record.get("kind") == "e2e_test" for record in records), records
