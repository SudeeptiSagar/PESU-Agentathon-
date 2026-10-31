"""Scripted typed demo runs shared by the e2e tests and ``python -m tests.e2e.run_demo``.

These runs use the real FastAPI app, the real WebSocket contract and real Playwright
through the agent. Only the language model and the profile are scripted. Each scenario
raises ``BlockedScenario`` while a required contract member is still a stub, so a caller
can report BLOCKED instead of turning stub behaviour into a pass.
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

from tests.e2e.harness import (
    ConsoleClient,
    FakeLLM,
    FixtureSite,
    PROFILE,
    app_server,
    assert_readback_safe,
    console_client,
    fake_llm,
    fake_profile,
    failure_with_log,
    fixture_config,
    fixture_site,
    redact,
    require_ready,
    tool,
)


def _fill(label: str, value_ref: str, fallback: str):
    def step(ctx):
        field_id = ctx.field_id(label, fallback)
        if not field_id:
            return tool("read_page", mode="fields")
        return tool("fill_field", field_id=field_id, value_ref=value_ref)
    return step


def _click(label: str, fallback: str):
    def step(ctx):
        element_id = ctx.button_id(label, fallback) or ctx.link_id(label, fallback)
        if not element_id:
            return tool("read_page", mode="fields")
        return tool("click", element_id=element_id)
    return step


A_SCRIPT: list[Any] = [
    tool("web_search", query="where was Kalpana Chawla born"),
    tool("navigate", target="e2e_article"),
    tool("read_page", mode="main_text"),
    tool("finish", summary="Kalpana Chawla was born in Karnal, Haryana, India."),
]

B_SCRIPT: list[Any] = [
    tool("navigate", target="e2e_portal"),
    _fill("full name", "{full_name}", "f1"),
    _fill("date of birth", "{dob}", "f2"),
    _fill("pin code", "{pin_code}", "f3"),
    _fill("aadhaar", "{aadhaar}", "f4"),
    tool("read_page", mode="fields"),
    _click("submit application", "b1"),
    _fill("pin code", "{pin_code}", "f3"),
    _click("submit application", "b1"),
    tool("read_page", mode="fields"),
]

C_SCRIPT: list[Any] = [
    tool("navigate", target="e2e_shop"),
    _click("add to cart", "b1"),
    tool("read_page", mode="summary"),
    _click("place order", "b2"),
]


@dataclasses.dataclass
class DemoRun:
    scenario: str
    site: FixtureSite
    fake: FakeLLM
    client: ConsoleClient


@contextlib.asynccontextmanager
async def _demo_run(scenario: str, script: Sequence[Any]) -> AsyncIterator[DemoRun]:
    require_ready(scenario)
    with contextlib.ExitStack() as stack:
        site = stack.enter_context(fixture_site())
        stack.enter_context(fixture_config(site))
        stack.enter_context(fake_profile())
        fake = stack.enter_context(fake_llm(script))
        async with app_server() as server:
            async with console_client(server) as client:
                yield DemoRun(scenario=scenario, site=site, fake=fake, client=client)


def _speak_texts(client: ConsoleClient, until_seq: int | None = None) -> list[str]:
    return [str(event.data.get("text", "")) for event in client.speaks()
            if until_seq is None or event.seq <= until_seq]


def _has_error_alert(client: ConsoleClient) -> bool:
    for event in client.events_of_type("alert"):
        if str(event.data.get("level", "")).casefold() == "error":
            return True
    return False


def _assert_steps(client: ConsoleClient, minimum: int) -> list[Any]:
    steps = client.events_of_type("step")
    assert len(steps) >= minimum, (
        f"expected at least {minimum} step events, got {len(steps)}"
    )
    for step in steps:
        missing = {"n", "action", "result"} - set(step.data)
        assert not missing, f"step event is missing {sorted(missing)}: {step.data}"
    return steps


async def scenario_a() -> str:
    """Task A: mock search -> article -> spoken answer containing Karnal."""
    async with _demo_run("A", A_SCRIPT) as run:
        client = run.client
        try:
            await client.wait_for_state("IDLE", timeout=15)
            await client.send_utterance("Find out where Kalpana Chawla was born.")
            answer = await client.wait_for_speak("Karnal", timeout=90)
            await client.wait_for_state("DONE", timeout=30)
            steps = _assert_steps(client, minimum=2)
            actions = [str(step.data.get("action", "")).casefold() for step in steps]
            assert any("search" in action for action in actions), (
                f"no search step was recorded: {actions}"
            )
            assert any("navigate" in action or "click" in action for action in actions), (
                f"no article navigation step was recorded: {actions}"
            )
            assert not _has_error_alert(client), "the agent emitted an error alert"
            run.fake.assert_no_sensitive_prompts()
            client.assert_no_sensitive_events()
            spoken = str(answer.data.get("text", ""))
            return (f"{len(steps)} step events; search and article navigation recorded; "
                    f"answer spoke: {spoken[:120]}")
        except Exception as exc:  # noqa: BLE001 - re-raised with diagnostics
            raise failure_with_log(exc, client, run.fake) from None


async def scenario_b() -> str:
    """Task B: portal fill, truncated PIN caught, human check, read-back, confirm."""
    async with _demo_run("B", B_SCRIPT) as run:
        client = run.client
        site = run.site
        try:
            await client.wait_for_state("IDLE", timeout=15)
            await client.send_utterance(
                "Apply for the disability pension on the demo portal."
            )

            await client.wait_for_human_check(timeout=120)
            assert site.portal_submissions == 0, (
                "the portal form was submitted before the human check and confirm"
            )
            assert site.portal_attempts == 0, (
                "a submit attempt happened before the human check and confirm"
            )

            site.mark_human_done()
            await asyncio.sleep(1.0)  # let the fixture page poll the human-done flag
            await client.send_utterance("done")
            pending = await client.wait_for_pending(timeout=90)
            pending_text = str(pending.data.get("description", "")).casefold()
            assert "submit" in pending_text or "application" in pending_text, (
                f"pending description does not name the submit action: {pending_text!r}"
            )

            instruction = await client.wait_for_speak(
                "Say confirm to go ahead, or say change followed by the field name.",
                timeout=60,
            )
            chunks = _speak_texts(client, until_seq=instruction.seq)
            assert_readback_safe(chunks)

            all_speaks = _speak_texts(client, until_seq=instruction.seq)
            evidence_texts = list(all_speaks)
            evidence_texts.extend(
                json.dumps(step.data, ensure_ascii=False)
                for step in client.events_of_type("step")
                if step.seq <= instruction.seq
            )
            pin_signal = False
            for text in evidence_texts:
                lowered = text.casefold()
                if "pin" not in lowered:
                    continue
                value_digits = re.sub(r"\D", "", text)
                if any(word in lowered for word in
                       ("wrong", "mismatch", "incorrect", "not match", "not the",
                        "cut off", "six digit", "6 digit", "corrected", "fix",
                        "should", "expected", "actual", "instead")):
                    pin_signal = True
                    break
                if PROFILE["pin_code"][:-1] in value_digits and (
                        PROFILE["pin_code"] not in value_digits):
                    pin_signal = True
                    break
            assert pin_signal, (
                "the agent did not report the truncated PIN code; speaks were: "
                f"{redact(repr(all_speaks))}"
            )
            assert site.portal_submissions == 0, (
                "the portal submitted before the user said confirm"
            )
            assert site.portal_attempts == 0, (
                "a submit attempt happened before the user said confirm"
            )

            confirm_event = await client.send_utterance("confirm")
            client.assert_no_irreversible_before_confirm(("submit",))
            acknowledgment = await client.wait_for_ack(timeout=60,
                                                        after_seq=confirm_event.seq)
            await site.wait_for_portal_submission(timeout=20)
            assert site.portal_attempts >= 1, "confirm did not trigger a submit click"
            compact = re.sub(r"[^A-Za-z0-9]", "", str(acknowledgment.data.get("text", "")))
            assert "ACK20260042" in compact.upper() or "ACKNOWLEDG" in compact.upper(), (
                f"acknowledgment number was not spoken: {acknowledgment.data!r}"
            )
            assert site.portal_submissions == 1, (
                f"expected exactly one portal submission, got {site.portal_submissions}"
            )
            assert not _has_error_alert(client), "the agent emitted an error alert"
            run.fake.assert_no_sensitive_prompts()
            client.assert_no_sensitive_events()
            return (f"PIN mismatch reported; human check paused and resumed; "
                    f"read-back safe with {len(chunks)} chunks; confirm committed once; "
                    f"acknowledgment {acknowledgment.data.get('text', '')[:80]!r}")
        except Exception as exc:  # noqa: BLE001 - re-raised with diagnostics
            raise failure_with_log(exc, client, run.fake) from None


async def scenario_c() -> str:
    """Task C: shop add, held Place order with total, no order, payment hand-off."""
    async with _demo_run("C", C_SCRIPT) as run:
        client = run.client
        site = run.site
        try:
            await client.wait_for_state("IDLE", timeout=15)
            await client.send_utterance("Order a pack of AA batteries from the demo shop.")

            pending = await client.wait_for_pending(timeout=120)
            description = str(pending.data.get("description", ""))
            lowered = description.casefold()
            assert "order" in lowered or "pay" in lowered, (
                f"pending description does not name the order action: {description!r}"
            )
            assert "249" in re.sub(r"\D", "", description), (
                f"pending description does not include the total 249: {description!r}"
            )
            assert site.shop_orders == 0, "the shop placed an order before confirm"

            pre_confirm_speaks = "\n".join(_speak_texts(client)).casefold()
            assert "order placed" not in pre_confirm_speaks, (
                "an order was announced before confirm"
            )
            assert "purchased" not in pre_confirm_speaks, (
                "a purchase was announced before confirm"
            )

            confirm_event = await client.send_utterance("confirm")
            client.assert_no_irreversible_before_confirm(("place order",))
            await site.wait_for_shop_order(timeout=20)
            assert site.shop_orders == 1, (
                f"expected exactly one shop order after confirm, got {site.shop_orders}"
            )
            handoff = await client.wait_for_payment_handoff(
                timeout=60, after_seq=confirm_event.seq
            )
            handoff_text = str(handoff.data.get("text") or handoff.data.get("name") or "")
            assert ("payment" in handoff_text.casefold()
                    or "hand" in handoff_text.casefold()
                    or "human" in handoff_text.casefold()
                    or handoff.data.get("name") == "NEEDS_HUMAN_CHECK"), (
                f"no payment hand-off was announced: {handoff.data!r}"
            )

            bad_steps = []
            for step in client.events_of_type("step"):
                action = str(step.data.get("action", "")).casefold()
                blob = json.dumps(step.data, ensure_ascii=False).casefold()
                if any(word in action for word in ("fill_field", "type_text")) and any(
                        word in blob for word in ("card", "cvv", "expiry")):
                    bad_steps.append(step.data)
            assert not bad_steps, (
                f"the agent typed payment details (human-only): {redact(str(bad_steps))}"
            )
            assert not _has_error_alert(client), "the agent emitted an error alert"
            run.fake.assert_no_sensitive_prompts()
            client.assert_no_sensitive_events()
            return (f"pending held Place order with total 249; no order before confirm; "
                    f"confirm placed exactly {site.shop_orders} order; payment hand-off: "
                    f"{handoff_text[:100]!r}")
        except Exception as exc:  # noqa: BLE001 - re-raised with diagnostics
            raise failure_with_log(exc, client, run.fake) from None


SCENARIOS = {"A": scenario_a, "B": scenario_b, "C": scenario_c}
