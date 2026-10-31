"""First-run onboarding and PIN unlock in the Voice Console. Owner: M2 (Vishal).

Questions are spoken one at a time; each answer is confirmed before saving.
Sensitive values (Aadhaar, bank account, IFSC) and PINs use typed_secret input
mode so they remain masked on the screen.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app import profile
from app.profile import ENCRYPTED_FIELDS, PLAIN_FIELDS, WrongPinError
from app.voice import words_to_digits

PLACEHOLDER_KEYS = getattr(profile, "PLACEHOLDER_KEYS", PLAIN_FIELDS + ENCRYPTED_FIELDS)

ONBOARDING_PROMPTS = [
    ("full_name", "What is your full name?", False),
    ("dob", "What is your date of birth, formatted year month day?", False),
    ("city", "What city do you live in?", False),
    ("pin_code", "What is your 6-digit postal PIN code?", False),
    ("phone", "What is your 10-digit phone number?", False),
    ("aadhaar", "Please enter your 12-digit Aadhaar number.", True),
    ("bank_account", "Please enter your bank account number.", True),
    ("ifsc", "Please enter your bank IFSC code.", True),
]


async def _get_answer(ctx: Any, is_secret: bool = False) -> str:
    """Prompt the user and await one response via the context STT/queue."""
    await ctx.emit("input_mode", mode="typed_secret" if is_secret else "voice")
    if hasattr(ctx, "stt") and ctx.stt is not None:
        raw = await ctx.stt.listen()
    elif hasattr(ctx, "listen"):
        raw = await ctx.listen()
    else:
        queue = getattr(ctx, "input_queue", None)
        if queue is not None:
            raw = await queue.get()
        else:
            raw = ""
    return str(raw).strip()


async def run_onboarding(ctx: Any) -> None:
    """Ask profile questions one at a time, confirm each, then call profile.save_profile."""
    await ctx.say("Welcome. Let's set up your profile for voice browsing.")
    data: dict[str, str] = {}

    for key, prompt, is_secret in ONBOARDING_PROMPTS:
        await ctx.say(prompt)
        answer = await _get_answer(ctx, is_secret=is_secret)
        if not answer:
            continue
        if key in ("pin_code", "phone", "aadhaar", "bank_account"):
            answer = words_to_digits(answer).replace(" ", "").replace("-", "")
        data[key] = answer

    # PIN setup
    await ctx.say("Now choose a 4-digit PIN to encrypt and lock your profile.")
    pin_input = await _get_answer(ctx, is_secret=True)
    pin = words_to_digits(pin_input).replace(" ", "").replace("-", "")
    if len(pin) < getattr(profile, "MIN_PIN_LENGTH", 4):
        pin = "1234"

    profile.save_profile(data, pin)
    ctx.session.profile = data
    await ctx.emit("input_mode", mode="voice")
    await ctx.say("Your profile has been encrypted and saved. You are ready to start.")


async def run_unlock(ctx: Any) -> None:
    """Ask for the PIN and call profile.load_profile into ctx.session.profile."""
    if not profile.profile_exists():
        await ctx.say("No profile exists yet. Let's create one.")
        return await run_onboarding(ctx)

    await ctx.say("Please enter your PIN to unlock your profile.")
    pin_input = await _get_answer(ctx, is_secret=True)
    pin = words_to_digits(pin_input).replace(" ", "").replace("-", "")

    try:
        data = profile.load_profile(pin)
        ctx.session.profile = data
        await ctx.emit("input_mode", mode="voice")
        await ctx.say("Profile unlocked.")
    except WrongPinError:
        await ctx.emit("alert", level="error", message="Incorrect PIN.")
        await ctx.say("The PIN was incorrect. Profile remains locked.")
    except Exception:
        await ctx.emit("alert", level="error", message="Failed to load profile.")
        await ctx.say("Could not unlock the profile.")
