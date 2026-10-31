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
    profile: dict = field(default_factory=dict)
    approved_domains: set[str] = field(default_factory=set)
    locators: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)
    pending_action: dict | None = None
    confirmed: bool = False
    failures: int = 0
    history: list = field(default_factory=list)
    saved_state: str | None = None


def transition(session: Session, new_state: str) -> None:
    """Move the session to new_state. Raises IllegalTransition on an illegal transition."""
    # STUB: CORE-06 (allowed-transitions table; COMMITTING needs confirmed and pending_action)
    if new_state not in STATES:
        raise IllegalTransition(f"unknown state {new_state!r}")
    if new_state == "COMMITTING" and not (session.confirmed and session.pending_action):
        raise IllegalTransition("COMMITTING needs confirmed=True and a pending_action")
    session.state = new_state


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
