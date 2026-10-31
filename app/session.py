"""Session state and the task state machine (PRD Section 12).

Owner: M1. Only this module's state machine may move to COMMITTING (hard rule 2).
"""
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

STATES = (
    "IDLE", "PLANNING", "ACTING", "VERIFYING", "READBACK", "AWAITING_CONFIRM",
    "COMMITTING", "DONE", "PAUSED", "NEEDS_USER", "NEEDS_HUMAN_CHECK",
)


class IllegalTransition(Exception):
    """Raised when a state change is not in the allowed-transitions table."""


@dataclass
class Session:
    state: str = "IDLE"
    goal: str | None = None
    plan: list[str] = field(default_factory=list)
    progress: list[str] = field(default_factory=list)
    # profile and expected hold real values: repr=False so printing or logging a Session
    # (or a failing assert showing one) can never reveal them (hard rule 4).
    profile: dict = field(default_factory=dict, repr=False)
    approved_domains: set[str] = field(default_factory=set)
    locators: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict, repr=False)
    # id -> {"kind","label",...} for the elements of the last snapshot, filled by
    # tools.record_snapshot. The executor uses it to know which controls are irreversible.
    elements: dict = field(default_factory=dict)
    pending_action: dict | None = None
    confirmed: bool = False
    failures: int = 0
    history: list = field(default_factory=list)
    saved_state: str | None = None


# Allowed moves. Two rules sit outside the table:
#  - Any state may go to IDLE ("stop" always works, hard rule 7). That clears the held action,
#    the confirmation and any saved state.
#  - PAUSED and NEEDS_HUMAN_CHECK remember where they came from (session.saved_state) and can
#    only go back there, or to IDLE.
TRANSITIONS: dict[str, frozenset[str]] = {
    "IDLE": frozenset({"PLANNING"}),
    "PLANNING": frozenset({"ACTING", "NEEDS_USER", "NEEDS_HUMAN_CHECK", "PAUSED", "DONE"}),
    "ACTING": frozenset({"VERIFYING", "AWAITING_CONFIRM", "NEEDS_USER", "NEEDS_HUMAN_CHECK",
                         "PAUSED", "DONE"}),
    "VERIFYING": frozenset({"READBACK", "ACTING", "NEEDS_USER", "PAUSED"}),
    "READBACK": frozenset({"AWAITING_CONFIRM", "ACTING", "PAUSED"}),
    "AWAITING_CONFIRM": frozenset({"COMMITTING", "ACTING", "NEEDS_USER", "PAUSED"}),
    "COMMITTING": frozenset({"DONE", "ACTING", "NEEDS_USER"}),
    "DONE": frozenset({"PLANNING"}),
    "NEEDS_USER": frozenset({"PLANNING", "ACTING"}),
    "PAUSED": frozenset(),             # exits: saved_state or IDLE
    "NEEDS_HUMAN_CHECK": frozenset(),  # exits: saved_state or IDLE
}
_REMEMBERS_ORIGIN = frozenset({"PAUSED", "NEEDS_HUMAN_CHECK"})
_NEEDS_PENDING = frozenset({"VERIFYING", "READBACK", "AWAITING_CONFIRM"})


def can_transition(session: Session, new_state: str) -> bool:
    """True if transition(session, new_state) would succeed."""
    try:
        _check(session, new_state)
    except IllegalTransition:
        return False
    return True


def _check(session: Session, new_state: str) -> None:
    old = session.state
    if new_state not in STATES:
        raise IllegalTransition(f"unknown state {new_state!r}")
    if old not in STATES:
        raise IllegalTransition(f"session is in unknown state {old!r}")
    if new_state == old or new_state == "IDLE":
        return
    if old in _REMEMBERS_ORIGIN:
        if new_state != session.saved_state:
            raise IllegalTransition(f"{old} can only resume {session.saved_state!r} or stop, not {new_state}")
    elif new_state not in TRANSITIONS[old]:
        raise IllegalTransition(f"{old} -> {new_state} is not allowed")
    if new_state in _NEEDS_PENDING and not session.pending_action:
        raise IllegalTransition(f"{new_state} needs a pending_action")
    if new_state == "COMMITTING" and not (session.confirmed and session.pending_action):
        raise IllegalTransition("COMMITTING needs confirmed=True (the user saying confirm) "
                                "and a pending_action")


def transition(session: Session, new_state: str) -> None:
    """Move the session to new_state. Raises IllegalTransition on an illegal transition.

    Hard rule 2: COMMITTING is reachable only from AWAITING_CONFIRM, with confirmed=True and a
    pending_action. The confirmation is single use: it is cleared on every other move out of
    AWAITING_CONFIRM, on entering it, and after COMMITTING.
    """
    _check(session, new_state)
    old = session.state
    if new_state == "IDLE":  # stop: drop everything that could still be acted on, even if already IDLE
        session.confirmed = False
        session.pending_action = None
        session.saved_state = None
        session.failures = 0
        session.state = "IDLE"
        return
    if new_state == old:
        return
    if new_state in _REMEMBERS_ORIGIN:
        session.saved_state = old
    elif old in _REMEMBERS_ORIGIN:
        session.saved_state = None
    if old == "AWAITING_CONFIRM" and new_state != "COMMITTING":
        session.confirmed = False
    if new_state == "AWAITING_CONFIRM":
        session.confirmed = False  # a fresh question needs a fresh "confirm"
    if old == "COMMITTING":
        session.confirmed = False
        session.pending_action = None
    session.state = new_state


def confirm(session: Session) -> None:
    """The user said "confirm". Only valid while AWAITING_CONFIRM; moves on to COMMITTING.

    Called from the backend's command matcher only, never from an LLM tool (hard rule 2).
    """
    if session.state != "AWAITING_CONFIRM":
        raise IllegalTransition(f"nothing to confirm in state {session.state}")
    session.confirmed = True
    try:
        transition(session, "COMMITTING")
    except IllegalTransition:
        session.confirmed = False
        raise


def resume(session: Session) -> str:
    """Leave PAUSED or NEEDS_HUMAN_CHECK and return to the state it came from. Returns that state."""
    if session.state not in _REMEMBERS_ORIGIN or not session.saved_state:
        raise IllegalTransition(f"nothing to resume in state {session.state}")
    target = session.saved_state
    transition(session, target)
    return target


Send = Callable[[dict], Awaitable[None]]


@dataclass
class Context:
    """Everything a task needs, passed as `ctx` to agent.py and onboarding.py.

    Built once per Console connection in main.py. `emit` sends a Section 12 event.
    """
    session: Session
    send: Send
    browser: Any = None   # browser.BrowserController
    tts: Any = None       # voice.PiperTTS for audio; None when TTS_BACKEND=browser

    async def emit(self, type: str, **payload: Any) -> None:
        """Send {"type": type, **payload} to the Voice Console."""
        await self.send({"type": type, **payload})

    async def say(self, text: str) -> None:
        """Show text in the Console (`speak` event, always) and voice it with Piper if enabled.

        With TTS_BACKEND=browser the Console voices the `speak` event itself.
        """
        await self.emit("speak", text=text)
        if self.tts is not None:
            await self.tts.speak(text)
