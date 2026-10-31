"""CORE-03: the scenarios and scoring in scripts/reliability_test.py (no model needed)."""
import importlib.util
from pathlib import Path

import httpx
import pytest

from app import llm as llm_mod
from app.profile import DEMO_PROFILE as _SAMPLE

_spec = importlib.util.spec_from_file_location(
    "reliability_test", Path(__file__).resolve().parent.parent / "scripts" / "reliability_test.py")
rt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt)

FILL = [rt.build_fill_case(i) for i in range(len(rt.FILL_CASES))]
CLICK = [rt.build_click_case(i) for i in range(len(rt.CLICK_CASES))]


def test_ten_scenarios_each():
    assert len(FILL) == 10 and len(CLICK) == 10


@pytest.mark.parametrize("case", FILL, ids=lambda c: c["label"])
def test_fill_scenario_is_well_formed(case):
    fields = case["snapshot"]["fields"]
    labels = [f["label"] for f in fields]
    assert len(set(labels)) == len(labels)                       # no duplicate labels
    assert [f["id"] for f in fields] == [f"f{n}" for n in range(1, len(fields) + 1)]
    target = next(f for f in fields if f["id"] == case["target_id"])
    assert target["label"] == case["label"]
    assert case["expected_ref"].strip("{}") in rt.PROFILE_KEYS


@pytest.mark.parametrize("case", CLICK, ids=lambda c: c["label"])
def test_click_scenario_has_exactly_one_correct_link(case):
    links = case["snapshot"]["links"]
    assert len({link["text"] for link in links}) == len(links)
    assert [link["text"] for link in links].count(case["label"]) == 1
    assert next(l for l in links if l["id"] == case["target_id"])["text"] == case["label"]
    assert all(len(link["text"]) < 80 for link in links)


def test_scenarios_are_deterministic_and_ids_are_shuffled():
    assert rt.build_fill_case(3) == rt.build_fill_case(3)
    assert rt.build_click_case(3) == rt.build_click_case(3)
    assert len({c["target_id"] for c in FILL}) > 1               # target not always in the same slot
    assert len({c["target_id"] for c in CLICK}) > 1


def test_prompt_contains_placeholders_and_untrusted_label_but_no_profile_values():
    text = " ".join(m["content"] for m in rt.messages_for(FILL[0]))
    assert "{dob}" in text and "untrusted" in text and "<page>" in text
    for key in ("full_name", "dob", "phone", "email", "aadhaar", "bank_account", "ifsc", "pin_code"):
        assert _SAMPLE[key] not in text


def test_judge_fill():
    case = FILL[1]
    good = {"name": "fill_field", "args": {"field_id": case["target_id"], "value_ref": "{dob}"}}
    assert rt.judge_fill(case, good)
    assert not rt.judge_fill(case, None)
    assert not rt.judge_fill(case, {**good, "name": "type_text"})
    assert not rt.judge_fill(case, {**good, "args": {**good["args"], "field_id": "f99"}})
    assert not rt.judge_fill(case, {**good, "args": {**good["args"], "value_ref": "dob"}})
    assert not rt.judge_fill(case, {**good, "args": {**good["args"], "value_ref": "{phone}"}})


def test_judge_click():
    case = CLICK[0]
    good = {"name": "click", "args": {"element_id": case["target_id"]}}
    assert rt.judge_click(case, good)
    assert not rt.judge_click(case, None)
    assert not rt.judge_click(case, {"name": "navigate", "args": {"target": "x"}})
    assert not rt.judge_click(case, {"name": "click", "args": {"element_id": "l99"}})


async def test_run_suite_counts_passes_and_failures(monkeypatch):
    answers = iter([{"name": "click", "args": {"element_id": c["target_id"]}} for c in CLICK[:8]]
                   + [{"name": "click", "args": {"element_id": "l99"}}, None])

    async def fake_llm(messages, tools=None):
        return {"text": None, "tool_call": next(answers)}

    monkeypatch.setattr(llm_mod, "llm", fake_llm)
    result = await rt.run_suite("click", CLICK, rt.judge_click)
    assert (result["passed"], result["total"]) == (8, 10)
    assert [r["ok"] for r in result["rows"]] == [True] * 8 + [False, False]
    assert result["rows"][9]["got"] == "no tool call"


async def test_run_suite_records_connection_errors_as_failures(monkeypatch):
    async def broken(messages, tools=None):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(llm_mod, "llm", broken)
    result = await rt.run_suite("fill_field", FILL[:2], rt.judge_fill)
    assert result["passed"] == 0 and "ConnectError" in result["rows"][0]["got"]


def test_report_flags_below_target_and_lists_failures():
    suites = [
        {"name": "fill_field", "passed": 10, "total": 10, "rows": [
            {"n": 1, "ok": True, "secs": 1.0, "label": "x", "got": "", "want": "f1"}]},
        {"name": "click", "passed": 7, "total": 10, "rows": [
            {"n": 1, "ok": False, "secs": 2.0, "label": "Some link", "got": "no tool call", "want": "l3"}]},
    ]
    text = rt.report("qwen3:8b", "0.9.0", suites)
    assert "`qwen3:8b`, Ollama 0.9.0" in text
    assert "fill_field: 10/10 (meets target)" in text
    assert "click: 7/10 (BELOW target)" in text
    assert "| 1 | Some link | l3 | `no tool call` |" in text
