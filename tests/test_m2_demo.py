"""Automated integration test for M2 MVP demonstration harness."""
import asyncio
import json
import pytest
from playwright.async_api import async_playwright

from scripts.m2_demo import TARGET_OVERLAY_SCRIPT, app, handle_user_command, M2HarnessSession


class MockWebSocket:
    def __init__(self):
        self.sent = []

    async def send_json(self, data: dict):
        self.sent.append(data)


@pytest.mark.asyncio
async def test_m2_harness_element_targeting_and_feedback():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        # Create a test page with buttons and inputs
        await page.set_content("""
            <!doctype html>
            <html>
            <body>
                <button id="tab-bank">Bank Details</button>
                <input id="full_name" type="text" />
                <button id="submit-btn">Submit</button>
            </body>
            </html>
        """)
        # Inject target cursor script
        await page.evaluate(TARGET_OVERLAY_SCRIPT)

        ws = MockWebSocket()
        dummy_bc = type("DummyBC", (), {"active": page, "refocus_console": lambda self: asyncio.sleep(0)})()
        session = M2HarnessSession(browser=dummy_bc, ws=ws)

        # 1. Target and click #tab-bank
        await session.target_and_act("#tab-bank", "Bank Details Tab", "click")
        assert any(e.get("type") == "step" and e.get("target") == "Bank Details Tab" for e in ws.sent)

        # 2. Target and fill #full_name
        await session.target_and_act("#full_name", "Full Name", "fill", "Ramesh Kumar")
        val = await page.input_value("#full_name")
        assert val == "Ramesh Kumar"

        # 3. Test command routing: Stop
        await handle_user_command("stop", session)
        assert any(e.get("type") == "state" and e.get("name") == "IDLE" for e in ws.sent)
        assert any(e.get("type") == "speak" and "Stopped" in e.get("text", "") for e in ws.sent)

        # 4. Test command routing: Help
        await handle_user_command("help", session)
        assert any(e.get("type") == "speak" and "You can say" in e.get("text", "") for e in ws.sent)

        # 5. Test command routing: Pause
        await handle_user_command("pause", session)
        assert any(e.get("type") == "state" and e.get("name") == "PAUSED" for e in ws.sent)

        # 6. Test irreversible action: Submit
        await handle_user_command("submit application", session)
        assert any(e.get("type") == "state" and e.get("name") == "AWAITING_CONFIRM" for e in ws.sent)
        assert any(e.get("type") == "pending" for e in ws.sent)

        # 7. Test confirmation: Confirm
        await handle_user_command("confirm", session)
        assert any(e.get("type") == "state" and e.get("name") == "DONE" for e in ws.sent)

        await browser.close()

