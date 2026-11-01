"""First-run onboarding and PIN unlock in the Voice Console. Owner: M2 (Vishal); rewritten by M1 (UI-07).

Onboarding asks for every detail the forms need, one at a time. Each answer is checked, read back and confirmed
(Aadhaar, bank account and IFSC are typed, hidden on screen, and only their last four characters are ever spoken). The PIN
that locks the profile is entered twice. Unlock gives three tries.

Questions use `await ctx.listen()`: while it waits, every sentence except "stop" is the answer. Nothing the user says here
is logged or put in an event or an exception message (hard rule 4). The Console is always returned to voice input at the
end, even if the user says "stop" in the middle of a hidden entry.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from app import profile
from app.profile import MIN_PIN_LENGTH, NoProfileError, ProfileCorruptError, WrongPinError
from app.voice import match_command, spoken_digits, words_to_digits

MAX_TRIES = 3
PIN_TRIES = 3
MONTHS = {name: n for n, names in enumerate(
    ("january jan", "february feb", "march mar", "april apr", "may", "june jun", "july jul", "august aug",
     "september sep sept", "october oct", "november nov", "december dec"), 1) for name in names.split()}
SKIP_WORDS = {"skip", "none", "no email", "nothing", "i have none"}


# ---------------------------------------------------------------- parsing and speaking (pure, unit-tested)
def _digits(raw: object) -> str:
    return re.sub(r"\D", "", words_to_digits(str(raw)))


def parse_text(raw: object) -> str | None:
    text = re.sub(r"\s+", " ", str(raw)).strip(" .,;")
    return " ".join(word[:1].upper() + word[1:] for word in text.split()) if len(text) >= 2 else None


def parse_address(raw: object) -> str | None:
    text = re.sub(r"\s+", " ", str(raw)).strip()
    return text[:1].upper() + text[1:] if len(text) >= 5 else None


def parse_date(raw: object, today: date | None = None) -> str | None:
    """A date of birth as YYYY-MM-DD, or None. Day first for numbers (04/03/1980 is 4 March), as in India."""
    today = today or date.today()
    text = words_to_digits(str(raw)).lower()
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text)
    text = re.sub(r"\b(of|the)\b", " ", text).replace(",", " ")
    text = re.sub(r"\s+", " ", text).strip()
    year = month = day = None
    if m := re.fullmatch(r"(\d{4})[-/. ](\d{1,2})[-/. ](\d{1,2})", text):
        year, month, day = (int(g) for g in m.groups())
    elif m := re.fullmatch(r"(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{4})", text):
        day, month, year = (int(g) for g in m.groups())
    elif m := re.fullmatch(r"(\d{1,2}) ([a-z]+) (\d{4})", text):
        day, month, year = int(m[1]), MONTHS.get(m[2]), int(m[3])
    elif m := re.fullmatch(r"([a-z]+) (\d{1,2}) (\d{4})", text):
        month, day, year = MONTHS.get(m[1]), int(m[2]), int(m[3])
    elif m := re.fullmatch(r"(\d{2})(\d{2})(\d{4})", text):
        day, month, year = (int(g) for g in m.groups())
    if not (year and month and day):
        return None
    try:
        born = date(year, month, day)
    except ValueError:
        return None
    return born.isoformat() if date(1900, 1, 1) <= born <= today else None


def spoken_date(iso: str) -> str:
    year, month, day = (int(p) for p in iso.split("-"))
    names = ("January February March April May June July August September October November December").split()
    return f"{day} {names[month - 1]} {year}"


def digits_parser(length: int | None = None, low: int | None = None, high: int | None = None,
                  min_len: int | None = None, max_len: int | None = None) -> Callable[[object], str | None]:
    def parse(raw: object) -> str | None:
        digits = _digits(raw)
        if not digits:
            return None
        if length is not None and len(digits) != length:
            return None
        if min_len is not None and len(digits) < min_len or max_len is not None and len(digits) > max_len:
            return None
        if low is not None and int(digits) < low or high is not None and int(digits) > high:
            return None
        return digits if length or min_len else str(int(digits))
    return parse


def choice_parser(options: dict[str, tuple[str, ...]]) -> Callable[[object], str | None]:
    """options: canonical value -> spoken forms. Matching ignores case, spaces and punctuation ("o b c" is "OBC")."""
    def squash(text: object) -> str:
        return re.sub(r"[^a-z]", "", str(text).lower())
    table = {squash(form): canonical for canonical, forms in options.items() for form in (canonical, *forms)}

    def parse(raw: object) -> str | None:
        return table.get(squash(raw))
    return parse


def parse_email(raw: object) -> str | None:
    text = str(raw).lower().strip()
    for spoken, symbol in ((" at ", "@"), (" dot ", "."), (" underscore ", "_"), (" dash ", "-"), (" hyphen ", "-")):
        text = text.replace(spoken, symbol)
    text = re.sub(r"\s+", "", text)
    return text if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s.]+", text) else None


def parse_ifsc(raw: object) -> str | None:
    text = re.sub(r"[\s-]", "", str(raw)).upper()
    return text if re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", text) else None


def say_digits(value: str) -> str:
    return spoken_digits(value)


def say_email(value: str) -> str:
    return value.replace("@", " at ").replace(".", " dot ")


@dataclass(frozen=True)
class Field:
    key: str
    prompt: str
    parse: Callable[[object], str | None]
    help: str
    speak: Callable[[str], str] = lambda value: value
    secret: bool = False
    optional: bool = False


GENDERS = {"Male": ("man", "m"), "Female": ("woman", "f"), "Transgender": ("other", "third gender")}
CATEGORIES = {"General": ("gen", "open"), "OBC": ("other backward class", "other backward classes"),
              "SC": ("scheduled caste",), "ST": ("scheduled tribe",)}

FIELDS: tuple[Field, ...] = (
    Field("full_name", "What is your full name?", parse_text, "Please say your full name."),
    Field("dob", "What is your date of birth? Say the day, the month name and the year.", parse_date,
          "Please say it like this: 4 March 1980.", speak=spoken_date),
    Field("gender", "Are you male, female, or transgender?", choice_parser(GENDERS),
          "Please say male, female, or transgender."),
    Field("address", "What is your street address?", parse_address, "Please say your street address."),
    Field("city", "Which city or town do you live in?", parse_text, "Please say the name of your city or town."),
    Field("state", "Which state do you live in?", parse_text, "Please say the name of your state."),
    Field("pin_code", "What is your 6 digit postal PIN code?", digits_parser(length=6),
          "The postal PIN code has exactly 6 digits.", speak=say_digits),
    Field("phone", "What is your 10 digit mobile number?", digits_parser(length=10),
          "A mobile number has exactly 10 digits.", speak=say_digits),
    Field("email", "What is your email address? Say skip if you do not have one.", parse_email,
          "Please say it like this: name at example dot com, or say skip.", speak=say_email, optional=True),
    Field("annual_income", "What is your family's yearly income in rupees? Say the digits.", digits_parser(low=0),
          "Please say the amount in digits, for example 1 2 0 0 0 0.", speak=say_digits),
    Field("category", "Which category are you in: general, O B C, S C, or S T?", choice_parser(CATEGORIES),
          "Please say general, O B C, S C, or S T."),
    Field("disability_percent", "What is your disability percentage, from 0 to 100?", digits_parser(low=0, high=100),
          "Please say a number from 0 to 100.", speak=say_digits),
    Field("aadhaar", "Please type your 12 digit Aadhaar number.", digits_parser(length=12),
          "An Aadhaar number has exactly 12 digits.", secret=True),
    Field("bank_account", "Please type your bank account number.", digits_parser(min_len=9, max_len=18),
          "A bank account number has 9 to 18 digits.", secret=True),
    Field("ifsc", "Please type your bank's IFSC code.", parse_ifsc,
          "An IFSC code is 4 letters, a zero, then 6 letters or digits, like SBIN0001234.", secret=True),
)
assert {f.key for f in FIELDS} == set(profile.PLACEHOLDER_KEYS), "onboarding must ask for every profile field"


# ---------------------------------------------------------------- conversation
async def get_answer(ctx: Any, secret: bool = False) -> str:
    """One answer from the user. Hidden-entry mode on the Console only while a secret is being typed."""
    await ctx.emit("input_mode", mode="typed_secret" if secret else "voice")
    try:
        return str(await ctx.listen()).strip()
    finally:
        if secret:
            await ctx.emit("input_mode", mode="voice")


async def yes_or_no(ctx: Any, question: str) -> bool:
    """Ask a yes/no question. Anything that is not clearly yes counts as no after one repeat."""
    await ctx.say(question)
    for _ in range(2):
        command = match_command(await get_answer(ctx))
        if command in ("yes", "no"):
            return command == "yes"
        await ctx.say("Please say yes or no.")
    return False


def read_back(field: Field, value: str) -> str:
    if field.secret:   # only the last four characters are ever spoken
        return f"I have a number ending {' '.join(value[-4:])}. Is that right?"
    return f"I heard {field.speak(value)}. Is that right?"


async def ask_field(ctx: Any, field: Field) -> str | None:
    """Ask, validate and confirm one field. None means it was skipped (optional) or could not be filled."""
    for attempt in range(MAX_TRIES):
        await ctx.say(field.prompt if attempt == 0 else "Let's try again. " + field.prompt)
        raw = await get_answer(ctx, secret=field.secret)
        if field.optional and (raw.lower().strip(" .") in SKIP_WORDS or match_command(raw) == "no"):
            return None
        value = field.parse(raw)
        if value is None:
            await ctx.say(field.help)
            continue
        if await yes_or_no(ctx, read_back(field, value)):
            return value
    return None


def clean_pin(raw: object) -> str:
    text = str(raw).strip()
    converted = words_to_digits(text)
    return re.sub(r"[\s-]", "", converted)


async def choose_pin(ctx: Any) -> str | None:
    for _ in range(PIN_TRIES):
        await ctx.say(f"Choose a PIN of at least {MIN_PIN_LENGTH} digits to lock your profile. Type it now.")
        pin = clean_pin(await get_answer(ctx, secret=True))
        if len(pin) < MIN_PIN_LENGTH:
            await ctx.say(f"That PIN is too short. It needs at least {MIN_PIN_LENGTH} digits.")
            continue
        await ctx.say("Type the same PIN again to confirm it.")
        if clean_pin(await get_answer(ctx, secret=True)) == pin:
            return pin
        await ctx.say("The two PINs were different.")
    return None


async def run_onboarding(ctx: Any) -> None:
    """Ask the profile questions one at a time, confirm each, choose a PIN, then save the encrypted profile."""
    try:
        await ctx.say("Welcome. Let's set up your profile so I can fill in forms for you. Say stop at any time. "
                      "Shall we start now?")
        if match_command(await get_answer(ctx)) != "yes":
            await ctx.say("Okay. I can still browse for you, but I cannot fill in forms until your profile is set up. "
                          "Restart me to set it up later.")
            return
        data: dict[str, str] = {}
        for field in FIELDS:
            value = await ask_field(ctx, field)
            if value is not None:
                data[field.key] = value
        if not data:
            await ctx.say("I did not get any details, so nothing was saved.")
            return
        pin = await choose_pin(ctx)
        if pin is None:
            await ctx.say("I could not set a PIN, so nothing was saved.")
            return
        try:
            profile.save_profile(data, pin)
        except Exception:                      # never include a detail or the PIN in a message
            await ctx.emit("alert", level="error", message="I could not save your profile.")
            await ctx.say("I could not save your profile.")
            return
        ctx.session.profile = data
        missing = [f.key.replace("_", " ") for f in FIELDS if f.key not in data and not f.optional]
        await ctx.say("Your profile is encrypted and saved. You are ready to start."
                      + (f" I did not get your {', '.join(missing)}; I will ask when a form needs it." if missing else ""))
    finally:
        await ctx.emit("input_mode", mode="voice")


async def run_unlock(ctx: Any) -> None:
    """Ask for the PIN (three tries) and load the profile into ctx.session.profile."""
    try:
        if not profile.profile_exists():
            return await run_onboarding(ctx)
        await ctx.say("Please type your PIN to unlock your profile.")
        for attempt in range(PIN_TRIES):
            pin = clean_pin(await get_answer(ctx, secret=True))
            try:
                data = profile.load_profile(pin)
            except WrongPinError:
                if attempt < PIN_TRIES - 1:
                    await ctx.say("That PIN was wrong. Please try again.")
                continue
            except NoProfileError:
                return await run_onboarding(ctx)
            except ProfileCorruptError:
                await ctx.emit("alert", level="error", message="The saved profile is damaged.")
                await ctx.say("Your saved profile is damaged, so I cannot unlock it.")
                return
            ctx.session.profile = data
            await ctx.say("Profile unlocked.")
            return
        await ctx.emit("alert", level="error", message="Too many wrong PINs.")
        await ctx.say("That was the third wrong PIN. Your profile stays locked. Restart me to try again.")
    finally:
        await ctx.emit("input_mode", mode="voice")
