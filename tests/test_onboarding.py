"""Tests for onboarding and profile PIN unlock (UI-07)."""
import asyncio
from types import SimpleNamespace
from pathlib import Path
import pytest

from app import config, onboarding, profile
from app.session import Session


class FakeContext:
    def __init__(self, inputs: list[str]):
        self.session = Session()
        self.spoken = []
        self.emitted = []
        self._inputs = list(inputs)

    async def say(self, text: str) -> None:
        self.spoken.append(text)

    async def emit(self, event_type: str, **kwargs) -> None:
        self.emitted.append({"type": event_type, **kwargs})

    async def listen(self) -> str:
        if self._inputs:
            return self._inputs.pop(0)
        return ""


def test_onboarding_and_unlock_flow(tmp_path, monkeypatch):
    import importlib
    importlib.reload(onboarding)
    profile_file = tmp_path / "user_profile.enc"
    monkeypatch.setattr(config, "PROFILE_PATH", str(profile_file))

    # Test answers for prompts:
    # full_name, dob, city, pin_code, phone, aadhaar, bank_account, ifsc, pin
    answers = [
        "Asha Rao",
        "1990-05-15",
        "Bengaluru",
        "5 6 0 0 0 1",
        "9876543210",
        "123412341234",
        "987654321012",
        "SBIN0001234",
        "4321",  # PIN
    ]

    ctx = FakeContext(answers)
    asyncio.run(onboarding.run_onboarding(ctx))

    assert profile.profile_exists()
    assert ctx.session.profile["full_name"] == "Asha Rao"
    assert ctx.session.profile["pin_code"] == "560001"
    assert any("encrypted and saved" in msg for msg in ctx.spoken)

    # Test unlock with correct PIN
    unlock_ctx = FakeContext(["4321"])
    asyncio.run(onboarding.run_unlock(unlock_ctx))
    assert bool(unlock_ctx.session.profile)
    assert any("Profile unlocked" in msg for msg in unlock_ctx.spoken)

    # Test unlock with wrong PIN ("0000" triggers WrongPinError in stub and real implementation)
    wrong_ctx = FakeContext(["0000"])
    asyncio.run(onboarding.run_unlock(wrong_ctx))
    assert wrong_ctx.session.profile == {}
    assert any("PIN was incorrect" in msg for msg in wrong_ctx.spoken)
