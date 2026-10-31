"""CORE-12: a held action is verified, read back from the real page, and pressed only after "confirm"."""
import json

import pytest

from app import agent
from app.profile import DEMO_PROFILE
from tests.test_agent import SNAP, World, call

URL = "http://localhost:8000/portal/apply.html"
EXPECTED = {
    "f1": {"label": "Full name", "selector": "#full_name", "value": "Ramesh Kumar", "type": "text",
           "source": "profile:full_name", "url": URL},
    "f3": {"label": "PIN code", "selector": "#pin", "value": "560001", "type": "pin_code",
           "source": "profile:pin_code", "url": URL},
    "f4": {"label": "Aadhaar number", "selector": "#aadhaar", "value": "000011112222", "type": "aadhaar",
           "source": "profile:aadhaar", "url": URL},
}
PIN_WRONG = {"field_id": "f3", "label": "PIN code", "expected": "560001", "actual": "56000", "kind": "mismatch"}
AADHAAR_WRONG = {"field_id": "f4", "label": "Aadhaar number", "expected": "********2222", "actual": "********2221",
                 "kind": "mismatch"}


@pytest.fixture
def w(monkeypatch):
    world = World(monkeypatch)
    world.verify_calls, world.verify_script = 0, []
    world.read_back_args = []

    async def fake_verify(page, session):
        world.verify_calls += 1
        item = world.verify_script.pop(0) if world.verify_script else []
        if isinstance(item, Exception):
            raise item
        return item

    def fake_build(session, actual_values):
        world.read_back_args.append(dict(actual_values))
        return ["Full name: Ramesh Kumar", "PIN code: 5 6 0 0 0 1", "Aadhaar number: ending 2 2 2 2",
                "Say confirm to go ahead, or say change followed by the field name."]

    monkeypatch.setattr(agent.verifier, "verify", fake_verify)
    monkeypatch.setattr(agent.readback, "build_readback", fake_build)
    monkeypatch.setattr(agent.readback, "describe_pending",
                        lambda session: "I'm about to press Submit application on demo portal.")

    world.form = True       # False: the held button is not part of a form

    async def executor(call_, session, browser):
        if world.form and not session.expected:       # the real executor records what it types; a new task clears it
            session.expected = json.loads(json.dumps(EXPECTED))
        if call_["name"] == "click":
            session.pending_action = {"element_id": "b1", "label": "Submit application", "kind": "submit",
                                      "url": URL, "domain": "localhost", "selector": "#b1"}
            return "held: 'Submit application' (submit) was NOT pressed."
        if call_["name"] == "finish":
            return "finish: " + call_["args"]["summary"]
        return "ok: done"
    world.executor.run = executor
    return world


def submit():
    return call("click", element_id="b1")


# ---------------------------------------------------------------- a clean form
async def test_a_clean_form_is_read_back_then_waits_for_confirm(w):
    w.llm_script = [submit()]
    await w.hear("apply for the pension")
    assert w.states() == ["PLANNING", "ACTING", "VERIFYING", "READBACK", "AWAITING_CONFIRM"]
    assert w.verify_calls == 1 and w.session.state == "AWAITING_CONFIRM" and w.session.pending_action
    pending = [e for e in w.events if e["type"] == "pending"]
    assert pending == [{"type": "pending", "description": "I'm about to press Submit application on demo portal."}]
    assert w.say() == ["I'm about to press Submit application on demo portal.",     # one speak event per chunk
                       "Full name: Ramesh Kumar", "PIN code: 5 6 0 0 0 1", "Aadhaar number: ending 2 2 2 2",
                       "Say confirm to go ahead, or say change followed by the field name."]


async def test_the_console_gets_a_field_table_with_sensitive_values_masked(w):
    w.llm_script = [submit()]
    await w.hear("apply")
    table = next(e for e in w.events if e["type"] == "field_table")["fields"]
    assert table == [{"label": "Full name", "value_masked": "Ramesh Kumar", "status": "ok"},
                     {"label": "PIN code", "value_masked": "560001", "status": "ok"},
                     {"label": "Aadhaar number", "value_masked": "****2222", "status": "ok"}]
    assert DEMO_PROFILE["aadhaar"] not in json.dumps(w.events)


async def test_event_order_is_state_then_table_then_pending_then_the_read_back(w):
    w.llm_script = [submit()]
    await w.hear("apply")
    tail = [e["type"] for e in w.events][-8:]
    assert tail == ["state", "field_table", "pending"] + ["speak"] * 5
    assert w.events[-1]["text"] == "Say confirm to go ahead, or say change followed by the field name."


async def test_the_read_back_uses_the_real_page_values_when_the_verifier_can_supply_them(w, monkeypatch):
    async def read_values(page, session):
        return {"f3": "560001", "f1": "Ramesh Kumar"}
    monkeypatch.setattr(agent.verifier, "read_values", read_values, raising=False)
    w.llm_script = [submit()]
    await w.hear("apply")
    assert w.read_back_args == [{"f3": "560001", "f1": "Ramesh Kumar"}]


async def test_a_failing_value_reader_does_not_stop_the_confirmation(w, monkeypatch):
    async def read_values(page, session):
        raise RuntimeError("page gone")
    monkeypatch.setattr(agent.verifier, "read_values", read_values, raising=False)
    w.llm_script = [submit()]
    await w.hear("apply")
    assert w.session.state == "AWAITING_CONFIRM" and w.read_back_args == [{}]


# ---------------------------------------------------------------- problems are reported and fixed
async def test_the_truncated_pin_is_reported_fixed_and_then_confirmed(w):
    w.verify_script = [[PIN_WRONG], []]                    # the planted trap, then clean after the refill
    w.llm_script = [submit(), call("fill_field", field_id="f3", value_ref="{pin_code}"), submit()]
    await w.hear("apply for the pension")
    problem_speech = next(t for t in w.say() if "looks wrong" in t)
    assert problem_speech == "PIN code looks wrong. The page shows 5 6 0 0 0 but I entered 5 6 0 0 0 1."
    assert w.states() == ["PLANNING", "ACTING", "VERIFYING", "ACTING", "VERIFYING", "READBACK", "AWAITING_CONFIRM"]
    assert w.verify_calls == 2 and w.ctx.verify_rounds == 0 and w.session.state == "AWAITING_CONFIRM"
    assert w.session.pending_action is not None            # held again by the second click


async def test_the_model_is_told_which_field_is_wrong_but_never_the_values(w):
    w.verify_script = [[PIN_WRONG, AADHAAR_WRONG], []]
    w.llm_script = [submit(), call("finish", summary="stopped for the test")]
    await w.hear("apply")
    prompt = json.dumps(w.prompts[1])                      # what the model saw on its next step
    assert "PIN code (mismatch)" in prompt and "Aadhaar number (mismatch)" in prompt
    assert "fill_field using its placeholder" in prompt and "not shown to you" in prompt
    for value in ("56000", "560001", "2221", "2222", "000011112222", "Ramesh Kumar"):
        assert value not in prompt, value


async def test_a_sensitive_mismatch_is_reported_without_any_digits(w):
    w.verify_script = [[AADHAAR_WRONG], []]
    w.llm_script = [submit(), call("finish", summary="x")]
    await w.hear("apply")
    spoken = [t for t in w.say() if "Aadhaar" in t][0]
    assert spoken == "Aadhaar number on the page does not match what I entered."
    table = [e for e in w.events if e["type"] == "field_table"][0]["fields"]
    assert {"label": "Aadhaar number", "value_masked": "****2221", "status": "mismatch"} in table


async def test_missing_and_error_problems_have_their_own_sentences(w):
    w.verify_script = [[{"field_id": "f1", "label": "Full name", "expected": "Ramesh Kumar", "actual": "", "kind": "missing"},
                        {"field_id": "f3", "label": "PIN code", "expected": "560001", "actual": "Enter 6 digits", "kind": "error"}],
                       []]
    w.llm_script = [submit(), call("finish", summary="x")]
    await w.hear("apply")
    spoken = [t for t in w.say() if "empty" in t][0]
    assert spoken == "Full name is empty on the page. PIN code shows an error. It says: Enter 6 digits."


async def test_problems_on_fields_the_agent_never_typed_still_appear_in_the_table(w):
    stray = {"field_id": "f9", "label": "Declaration", "expected": "", "actual": "", "kind": "missing"}
    w.verify_script = [[stray], []]
    w.llm_script = [submit(), call("finish", summary="x")]
    await w.hear("apply")
    table = [e for e in w.events if e["type"] == "field_table"][0]["fields"]
    assert {"label": "Declaration", "value_masked": "****", "status": "missing"} in table


async def test_the_held_action_is_dropped_while_the_form_is_being_fixed(w):
    w.verify_script = [[PIN_WRONG]]
    w.llm_script = [submit(), call("scroll", direction="down")]
    w.executor.run, original = w.executor.run, w.executor.run

    async def watch(call_, session, browser):
        if call_["name"] == "scroll":
            assert session.pending_action is None and session.state == "ACTING"
            return "finish: stopping"
        return await original(call_, session, browser)
    w.executor.run = watch
    await w.hear("apply")
    assert w.session.state == "DONE"


async def test_three_failed_checks_in_a_row_ask_the_user_for_help(w):
    w.verify_script = [[PIN_WRONG]] * 3
    fix = call("fill_field", field_id="f3", value_ref="{pin_code}")
    w.llm_script = [submit(), fix, submit(), fix, submit()]
    await w.hear("apply")
    assert w.verify_calls == 3 and w.session.state == "NEEDS_USER"
    assert w.say()[-1] == "I still cannot get the form right. What should I do?"
    assert w.ctx.verify_rounds == 0 and w.session.pending_action is None


async def test_a_form_check_that_cannot_run_is_a_problem_not_a_pass(w):
    w.verify_script = [RuntimeError("page closed"), []]
    w.llm_script = [submit(), call("fill_field", field_id="f1", value_ref="{full_name}"), submit()]
    await w.hear("apply")
    assert "I could not check the form against what I entered." in w.say()
    assert "The form check (unavailable)" in json.dumps(w.prompts[1])
    assert w.verify_calls == 2 and w.session.state == "AWAITING_CONFIRM"        # only the second, clean check passes


async def test_a_new_task_starts_the_verify_count_again(w):
    w.ctx.verify_rounds = 2
    w.llm_script = [call("finish", summary="ok")]
    await w.hear("something else")
    assert w.ctx.verify_rounds == 0


# ---------------------------------------------------------------- not a form
async def test_a_plain_button_is_described_without_a_form_check(w):
    w.form = False
    w.llm_script = [submit()]
    await w.hear("delete this message")
    assert w.verify_calls == 0 and w.states() == ["PLANNING", "ACTING", "AWAITING_CONFIRM"]
    assert w.say()[-1] == "I'm about to press Submit application on demo portal. Say confirm to go ahead, or no."
    assert [e for e in w.events if e["type"] == "pending"] and not [e for e in w.events if e["type"] == "field_table"]


# ---------------------------------------------------------------- nothing is pressed without "confirm"
async def test_nothing_is_pressed_until_confirm_and_then_only_once(w, monkeypatch):
    pressed = []

    async def commit(session, browser):
        pressed.append(session.state)
        session.pending_action, session.confirmed = None, False
        return "ok: pressed 'Submit application'"
    monkeypatch.setattr(agent.tools, "commit_pending", commit)
    w.llm_script = [submit(), call("finish", summary="Your acknowledgment number is 42.")]
    await w.hear("apply")
    for word in ("yes", "go ahead", "proceed", "approve", "submit it"):
        await w.hear(word)
    assert pressed == [] and w.session.state in ("AWAITING_CONFIRM", "ACTING", "DONE")
    if w.session.state != "AWAITING_CONFIRM":                # a non-confirm sentence sends the model back to work
        w.session.state, w.session.pending_action = "IDLE", None
        w.llm_script = [submit()]
        await w.hear("apply again")
    await w.hear("confirm")
    assert pressed == ["COMMITTING"]
    await w.hear("confirm")
    assert pressed == ["COMMITTING"]                         # the confirmation is single use


async def test_change_the_pin_returns_to_work_and_nothing_is_pressed(w, monkeypatch):
    async def never(session, browser):
        raise AssertionError("must not be pressed")
    monkeypatch.setattr(agent.tools, "commit_pending", never)
    w.llm_script = [submit()]
    await w.hear("apply")
    w.llm_script = [call("finish", summary="ok")]
    await w.hear("change the PIN code")
    assert w.session.pending_action is None and w.session.state == "DONE"
    assert "did not confirm and said: change the PIN code" in w.prompts[-1][1]["content"]


async def test_a_form_problem_also_raises_a_warning_alert_for_the_console(w):
    w.verify_script = [[PIN_WRONG], []]
    w.llm_script = [submit(), call("fill_field", field_id="f3", value_ref="{pin_code}"), submit()]
    await w.hear("apply")
    alerts = [e for e in w.events if e["type"] == "alert"]
    assert alerts == [{"type": "alert", "level": "warning",
                       "message": "PIN code looks wrong. The page shows 5 6 0 0 0 but I entered 5 6 0 0 0 1."}]
    order = [e["type"] for e in w.events]
    assert order.index("field_table") < order.index("alert") < order.index("speak", order.index("alert"))


async def test_the_alert_for_a_sensitive_mismatch_has_no_digits(w):
    w.verify_script = [[AADHAAR_WRONG], []]
    w.llm_script = [submit(), call("finish", summary="x")]
    await w.hear("apply")
    alert = next(e for e in w.events if e["type"] == "alert")
    assert alert["message"] == "Aadhaar number on the page does not match what I entered."
    assert not any(ch.isdigit() for ch in alert["message"])
