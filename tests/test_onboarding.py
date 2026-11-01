"""UI-07: onboarding and PIN unlock. The conversation is driven by scripted answers; nothing here touches ~/.voiceagent."""
import asyncio
import json
from datetime import date

import pytest

from app import agent, config, onboarding, profile
from app.onboarding import FIELDS
from app.session import Context, Session

SECRETS = {"aadhaar": "000011112222", "bank_account": "000000001234", "ifsc": "TEST0000001"}
PIN = "4829"


class FakeCtx:
    """Answers come from a script. Records everything said and emitted, in order."""

    def __init__(self, answers):
        self.session = Session()
        self.answers = list(answers)
        self.spoken, self.events = [], []

    async def say(self, text):
        self.spoken.append(text)

    async def emit(self, type, **payload):
        self.events.append({"type": type, **payload})

    async def listen(self):
        assert self.answers, f"asked more questions than expected; last said: {self.spoken[-1]!r}"
        return self.answers.pop(0)

    def modes(self):
        return [e["mode"] for e in self.events if e["type"] == "input_mode"]


RAW = {
    "full_name": "ramesh kumar", "dob": "4 March 1980", "gender": "male", "address": "12 MG Road", "city": "bengaluru",
    "state": "karnataka", "pin_code": "5 6 0 0 0 1", "phone": "9876543210", "email": "ramesh at example dot com",
    "annual_income": "120000", "category": "general", "disability_percent": "75", **SECRETS,
}


def happy(overrides=None, skip=(), pin=(PIN, PIN)):
    """The answers for a complete, clean run: welcome, every field plus its confirmation, then the PIN twice."""
    raw = {**RAW, **(overrides or {})}
    answers = ["yes"]
    for field in FIELDS:
        if field.key in skip:
            answers += ["skip"]
        else:
            answers += [raw[field.key], "yes"]
    return answers + list(pin)


def everything_said(ctx) -> str:
    return json.dumps([ctx.spoken, ctx.events])


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    monkeypatch.setattr(profile, "KDF_ITERATIONS", 1_000)


# ---------------------------------------------------------------- parsing
@pytest.mark.parametrize("raw,expected", [
    ("4 March 1980", "1980-03-04"), ("04/03/1980", "1980-03-04"), ("1980-03-04", "1980-03-04"),
    ("March 4th, 1980", "1980-03-04"), ("4th of March 1980", "1980-03-04"), ("04031980", "1980-03-04"),
    ("4 3 1980", "1980-03-04"), ("29 February 2000", "2000-02-29"), ("1 jan 1900", "1900-01-01"),
    ("31 February 1990", None), ("29 February 2001", None), ("4 Marchh 1980", None), ("1980", None),
    ("4 March 2999", None), ("4 March 1899", None), ("", None), ("tomorrow", None),
])
def test_parse_date(raw, expected):
    assert onboarding.parse_date(raw, today=date(2026, 11, 1)) == expected


def test_a_date_of_today_is_allowed_and_tomorrow_is_not():
    assert onboarding.parse_date("1 November 2026", today=date(2026, 11, 1)) == "2026-11-01"
    assert onboarding.parse_date("2 November 2026", today=date(2026, 11, 1)) is None


@pytest.mark.parametrize("parser,raw,expected", [
    (onboarding.digits_parser(length=6), "5 6 0 0 0 1", "560001"),
    (onboarding.digits_parser(length=6), "five six zero zero zero one", "560001"),
    (onboarding.digits_parser(length=6), "56000", None),
    (onboarding.digits_parser(length=6), "5600011", None),
    (onboarding.digits_parser(length=10), "98765-43210", "9876543210"),
    (onboarding.digits_parser(length=12), "0000 1111 2222", "000011112222"),
    (onboarding.digits_parser(low=0), "120000", "120000"),
    (onboarding.digits_parser(low=0), "0120000", "120000"),
    (onboarding.digits_parser(low=0), "none", None),
    (onboarding.digits_parser(low=0, high=100), "75", "75"),
    (onboarding.digits_parser(low=0, high=100), "101", None),
    (onboarding.digits_parser(min_len=9, max_len=18), "12345678", None),
    (onboarding.digits_parser(min_len=9, max_len=18), "000000001234", "000000001234"),
    (onboarding.digits_parser(min_len=9, max_len=18), "1" * 19, None),
])
def test_digit_parsers(parser, raw, expected):
    assert parser(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("male", "Male"), ("Man", "Male"), ("FEMALE", "Female"), ("woman", "Female"), ("transgender", "Transgender"),
    ("other", "Transgender"), ("banana", None), ("", None),
])
def test_gender(raw, expected):
    assert onboarding.choice_parser(onboarding.GENDERS)(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("general", "General"), ("O B C", "OBC"), ("obc", "OBC"), ("S C", "SC"), ("scheduled caste", "SC"),
    ("S.T.", "ST"), ("scheduled tribe", "ST"), ("rich", None),
])
def test_category(raw, expected):
    assert onboarding.choice_parser(onboarding.CATEGORIES)(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("ramesh at example dot com", "ramesh@example.com"), ("Ramesh.Kumar@Example.COM", "ramesh.kumar@example.com"),
    ("a dash b underscore c at mail dot co dot in", "a-b_c@mail.co.in"), ("ramesh", None), ("ramesh@", None),
    ("two@@example.com", None), ("a b@example.com", "ab@example.com"),
])
def test_email(raw, expected):
    assert onboarding.parse_email(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("SBIN0001234", "SBIN0001234"), ("sbin 0001234", "SBIN0001234"), ("HDFC0-004321", "HDFC0004321"),
    ("SBIN1001234", None), ("SBI0001234", None), ("SBIN000123", None), ("1234SBIN000", None),
])
def test_ifsc(raw, expected):
    assert onboarding.parse_ifsc(raw) == expected


def test_text_and_address():
    assert onboarding.parse_text("  asha   rao. ") == "Asha Rao"
    assert onboarding.parse_text("O'Brien McDonald") == "O'Brien McDonald"     # never lowercases what is already right
    assert onboarding.parse_text("a") is None and onboarding.parse_text("   ") is None
    assert onboarding.parse_address("12 mg road") == "12 mg road".capitalize()
    assert onboarding.parse_address("12") is None


def test_every_profile_field_is_asked_and_the_secret_ones_are_typed():
    assert [f.key for f in FIELDS if f.secret] == ["aadhaar", "bank_account", "ifsc"]
    assert {f.key for f in FIELDS} == set(profile.PLACEHOLDER_KEYS)
    assert [f.key for f in FIELDS if f.optional] == ["email"]


def test_spoken_forms():
    assert onboarding.spoken_date("1980-03-04") == "4 March 1980"
    assert onboarding.say_digits("560001") == "5 6 0 0 0 1"
    assert onboarding.say_email("ramesh@example.com") == "ramesh at example dot com"


# ---------------------------------------------------------------- a full onboarding
async def test_a_full_run_saves_every_field_in_the_form_the_portal_expects():
    ctx = FakeCtx(happy())
    await onboarding.run_onboarding(ctx)
    assert profile.profile_exists() and ctx.answers == []
    saved = profile.load_profile(PIN)
    assert saved == ctx.session.profile
    assert saved == {
        "full_name": "Ramesh Kumar", "dob": "1980-03-04", "gender": "Male", "address": "12 MG Road",
        "city": "Bengaluru", "state": "Karnataka", "pin_code": "560001", "phone": "9876543210",
        "email": "ramesh@example.com", "annual_income": "120000", "category": "General", "disability_percent": "75",
        **SECRETS}
    assert "Your profile is encrypted and saved." in ctx.spoken[-1] and "did not get" not in ctx.spoken[-1]


async def test_non_secret_answers_are_read_back_with_spaced_digits_and_dates_spoken_naturally():
    ctx = FakeCtx(happy())
    await onboarding.run_onboarding(ctx)
    said = " | ".join(ctx.spoken)
    assert "I heard 5 6 0 0 0 1. Is that right?" in said
    assert "I heard 4 March 1980. Is that right?" in said
    assert "I heard ramesh at example dot com. Is that right?" in said
    assert "I heard 9 8 7 6 5 4 3 2 1 0. Is that right?" in said


async def test_secrets_are_never_spoken_or_emitted_only_their_last_four():
    ctx = FakeCtx(happy())
    await onboarding.run_onboarding(ctx)
    blob = everything_said(ctx)
    for value in (*SECRETS.values(), PIN):
        assert value not in blob, value
    assert "I have a number ending 2 2 2 2. Is that right?" in ctx.spoken           # aadhaar
    assert "I have a number ending 1 2 3 4. Is that right?" in ctx.spoken           # bank account
    assert "I have a number ending 0 0 0 1. Is that right?" in ctx.spoken           # ifsc
    assert not any(ch in blob for ch in ("0000 1111", "00001111"))


async def test_hidden_entry_is_on_only_while_a_secret_is_typed_and_ends_in_voice_mode():
    ctx = FakeCtx(happy())
    await onboarding.run_onboarding(ctx)
    modes = ctx.modes()
    assert modes[-1] == "voice" and modes.count("typed_secret") == 3 + 2      # three details and the PIN twice
    for previous, current in zip(modes, modes[1:]):
        assert not (previous == current == "typed_secret")                    # never stuck in hidden mode between answers


# ---------------------------------------------------------------- mistakes and retries
async def test_an_invalid_answer_gets_help_and_another_try():
    ctx = FakeCtx(happy())
    ctx.answers[ctx.answers.index("5 6 0 0 0 1"):ctx.answers.index("5 6 0 0 0 1")] = ["56000"]      # a truncated PIN code first
    await onboarding.run_onboarding(ctx)
    assert "The postal PIN code has exactly 6 digits." in ctx.spoken
    assert profile.load_profile(PIN)["pin_code"] == "560001"


async def test_a_no_to_the_read_back_asks_the_question_again():
    answers = happy()
    i = answers.index("ramesh kumar")
    answers[i:i + 2] = ["ramesh kummar", "no", "ramesh kumar", "yes"]
    ctx = FakeCtx(answers)
    await onboarding.run_onboarding(ctx)
    assert profile.load_profile(PIN)["full_name"] == "Ramesh Kumar"
    assert sum(1 for t in ctx.spoken if t.endswith("What is your full name?")) == 2


async def test_a_field_that_fails_three_times_is_left_out_and_named_at_the_end():
    answers = happy()
    i = answers.index("4 March 1980")
    answers[i:i + 2] = ["someday", "never", "whenever"]
    ctx = FakeCtx(answers)
    await onboarding.run_onboarding(ctx)
    saved = profile.load_profile(PIN)
    assert "dob" not in saved and len(saved) == 14
    assert "I did not get your dob; I will ask when a form needs it." in ctx.spoken[-1]


async def test_the_optional_email_can_be_skipped_without_complaint():
    ctx = FakeCtx(happy(skip=("email",)))
    await onboarding.run_onboarding(ctx)
    saved = profile.load_profile(PIN)
    assert "email" not in saved and len(saved) == 14
    assert "did not get" not in ctx.spoken[-1]


@pytest.mark.parametrize("word", ["skip", "none", "no", "nothing"])
async def test_email_skip_words(word):
    answers = happy(skip=("email",))
    answers[answers.index("skip")] = word
    ctx = FakeCtx(answers)
    await onboarding.run_onboarding(ctx)
    assert "email" not in profile.load_profile(PIN)


async def test_a_confirmation_that_is_neither_yes_nor_no_is_asked_again_then_treated_as_no():
    answers = happy()
    i = answers.index("ramesh kumar")
    answers[i:i + 2] = ["ramesh kumar", "maybe", "perhaps", "ramesh kumar", "yes"]
    ctx = FakeCtx(answers)
    await onboarding.run_onboarding(ctx)
    assert ctx.spoken.count("Please say yes or no.") == 2
    assert profile.load_profile(PIN)["full_name"] == "Ramesh Kumar"


@pytest.mark.parametrize("word", ["approve", "proceed", "confirm", "ok"])
async def test_only_yes_counts_as_yes(word):
    ctx = FakeCtx([word, "no"])
    assert await onboarding.yes_or_no(ctx, "Is that right?") is False


# ---------------------------------------------------------------- the PIN
async def test_a_short_pin_is_refused_and_the_default_1234_is_never_used():
    ctx = FakeCtx(happy(pin=("12", "123", "4829", "4829")))
    await onboarding.run_onboarding(ctx)
    assert ctx.spoken.count("That PIN is too short. It needs at least 4 digits.") == 2
    assert profile.load_profile("4829")
    with pytest.raises(profile.WrongPinError):
        profile.load_profile("1234")


async def test_an_empty_pin_saves_nothing():
    ctx = FakeCtx(happy(pin=("", "", "")))
    await onboarding.run_onboarding(ctx)
    assert not profile.profile_exists() and ctx.session.profile == {}
    assert ctx.spoken[-1] == "I could not set a PIN, so nothing was saved."


async def test_a_pin_must_be_typed_twice_the_same():
    ctx = FakeCtx(happy(pin=("4829", "4820", "4829", "4829")))
    await onboarding.run_onboarding(ctx)
    assert "The two PINs were different." in ctx.spoken
    assert profile.load_profile("4829")


async def test_three_mismatched_pins_save_nothing():
    ctx = FakeCtx(happy(pin=("4829", "1111", "4829", "2222", "4829", "3333")))
    await onboarding.run_onboarding(ctx)
    assert not profile.profile_exists() and ctx.spoken[-1] == "I could not set a PIN, so nothing was saved."


async def test_a_spoken_pin_is_accepted():
    ctx = FakeCtx(happy(pin=("four eight two nine", "4 8 2 9")))
    await onboarding.run_onboarding(ctx)
    assert profile.load_profile("4829")


# ---------------------------------------------------------------- declining, stopping, failing
async def test_declining_to_start_saves_nothing_and_says_how_to_do_it_later():
    ctx = FakeCtx(["no"])
    await onboarding.run_onboarding(ctx)
    assert not profile.profile_exists() and ctx.session.profile == {}
    assert "cannot fill in forms until your profile is set up" in ctx.spoken[-1]
    assert ctx.modes()[-1] == "voice"


async def test_stopping_in_the_middle_of_a_hidden_entry_returns_the_console_to_voice_mode():
    ctx = Context(session=Session(), send=_collect(events := []))
    task = ctx.setup_task = asyncio.create_task(onboarding.run_onboarding(ctx))    # as main.py starts it
    feeder = ["yes"]
    for field in FIELDS:
        if field.secret:
            break
        feeder += [RAW[field.key], "yes"]
    for answer in feeder:
        await _answer(ctx, answer)
    await _until(lambda: ctx.listening and any(e == {"type": "input_mode", "mode": "typed_secret"} for e in events))
    await agent.stop(ctx)                                    # the user says stop while typing the Aadhaar number
    assert task.cancelled() or task.done()
    assert [e["mode"] for e in events if e["type"] == "input_mode"][-1] == "voice"
    assert not profile.profile_exists() and ctx.listening is False and ctx.setup_task is None


async def test_a_failure_to_save_is_an_alert_without_any_detail(monkeypatch):
    def boom(data, pin):
        raise OSError(f"disk full while saving {data['aadhaar']} with pin {pin}")
    monkeypatch.setattr(profile, "save_profile", boom)
    ctx = FakeCtx(happy())
    await onboarding.run_onboarding(ctx)
    assert ctx.session.profile == {} and ctx.spoken[-1] == "I could not save your profile."
    assert SECRETS["aadhaar"] not in everything_said(ctx) and PIN not in everything_said(ctx)


async def test_a_run_where_nothing_was_answered_saves_nothing():
    answers = ["yes"]
    for field in FIELDS:
        answers += ["?"] * 3 if not field.optional else ["skip"]        # nothing any field accepts
    ctx = FakeCtx(answers)
    await onboarding.run_onboarding(ctx)
    assert not profile.profile_exists() and ctx.spoken[-1] == "I did not get any details, so nothing was saved."


# ---------------------------------------------------------------- unlock
def saved_profile(tmp=None):
    profile.save_profile({"full_name": "Asha Rao", "dob": "1990-05-15"}, PIN)


async def test_unlock_with_the_right_pin():
    saved_profile()
    ctx = FakeCtx([PIN])
    await onboarding.run_unlock(ctx)
    assert ctx.session.profile == {"full_name": "Asha Rao", "dob": "1990-05-15"}
    assert ctx.spoken[-1] == "Profile unlocked." and ctx.modes() == ["typed_secret", "voice", "voice"]


async def test_unlock_gives_three_tries():
    saved_profile()
    ctx = FakeCtx(["1111", "2222", PIN])
    await onboarding.run_unlock(ctx)
    assert ctx.spoken.count("That PIN was wrong. Please try again.") == 2
    assert ctx.session.profile and ctx.spoken[-1] == "Profile unlocked."


async def test_three_wrong_pins_lock_it_with_a_clear_message():
    saved_profile()
    ctx = FakeCtx(["1111", "2222", "3333"])
    await onboarding.run_unlock(ctx)
    assert ctx.session.profile == {}
    assert ctx.spoken[-1] == "That was the third wrong PIN. Your profile stays locked. Restart me to try again."
    assert {"type": "alert", "level": "error", "message": "Too many wrong PINs."} in ctx.events
    assert ctx.modes()[-1] == "voice"
    blob = everything_said(ctx)
    assert not any(wrong in blob for wrong in ("1111", "2222", "3333"))


async def test_a_spoken_pin_unlocks():
    saved_profile()
    ctx = FakeCtx(["four eight two nine"])
    await onboarding.run_unlock(ctx)
    assert ctx.session.profile


async def test_a_damaged_profile_file_is_reported_not_guessed_at():
    saved_profile()
    path = config.PROFILE_PATH
    path.write_text("not json", encoding="utf-8")
    ctx = FakeCtx([PIN])
    await onboarding.run_unlock(ctx)
    assert ctx.spoken[-1] == "Your saved profile is damaged, so I cannot unlock it."
    assert {"type": "alert", "level": "error", "message": "The saved profile is damaged."} in ctx.events


async def test_unlock_with_no_profile_offers_onboarding():
    ctx = FakeCtx(["no"])
    await onboarding.run_unlock(ctx)
    assert ctx.spoken[0].startswith("Welcome.")


# ---------------------------------------------------------------- through the real Context and agent routing
def _collect(events):
    async def send(event):
        events.append(event)
    return send


async def _until(condition, limit=200):
    for _ in range(limit):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition never became true")


async def _answer(ctx, text):
    await _until(lambda: ctx.listening)
    await agent.handle_utterance(text, ctx)
    await _until(lambda: not ctx.listening or ctx.inbox.empty())
    await asyncio.sleep(0)


async def test_the_whole_conversation_works_through_the_agents_routing():
    events = []
    ctx = Context(session=Session(), send=_collect(events))
    ctx.setup_task = asyncio.create_task(onboarding.run_unlock(ctx))      # what main.py starts on the first connection
    for answer in happy():
        await _answer(ctx, answer)
    await asyncio.wait_for(ctx.setup_task, 10)
    assert ctx.session.state == "IDLE" and ctx.session.goal is None        # none of it started a task
    assert profile.load_profile(PIN)["full_name"] == "Ramesh Kumar"
    assert not any(e["type"] == "step" for e in events)
    blob = json.dumps(events)
    assert not any(secret in blob for secret in (*SECRETS.values(), PIN))
