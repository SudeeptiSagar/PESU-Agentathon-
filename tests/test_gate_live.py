"""Live Jev smoke test. Skipped unless JEV_API_KEY is set.

This is deliberately separate from the offline suite: it needs a real OpenCode
Console / TypeSafe credential and a network call. It never prints the key.
"""
import os

import pytest

from app import config, gate

pytestmark = pytest.mark.skipif(
    not os.getenv("JEV_API_KEY"),
    reason="JEV_API_KEY is not set; live Jev smoke test skipped",
)


@pytest.mark.asyncio
async def test_live_jev_navigate_uses_system_one(monkeypatch):
    monkeypatch.setattr(config, "GATE_BACKEND", "jev")
    monkeypatch.setattr(config, "JEV_API_KEY", os.environ["JEV_API_KEY"])
    action = {
        "name": "navigate",
        "args": {"target": "https://en.wikipedia.org/wiki/Kalpana_Chawla"},
    }
    context = {
        "goal": "Find out where Kalpana Chawla was born.",
        "domain": "en.wikipedia.org",
        "approved_domains": set(),
        "element": {},
        "history_tail": ["web_search: Kalpana Chawla birthplace"],
        "page": "Search results for Kalpana Chawla; the first result is her Wikipedia article.",
    }
    result = await gate.check(action, context)
    assert result["backend"] == "jev", result
    assert result["decision"] in {"proceed", "ask_user", "block"}, result
    assert "serves_goal" in result["reason"] and "injection" in result["reason"]
    assert 0.0 <= result["p"] <= 1.0
