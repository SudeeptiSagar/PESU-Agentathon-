"""Speech input and output, command matcher, digit helpers (PRD Sections 8 and 12).

Owner: M2 (Vishal). CORE-01 contract stubs; replace the bodies, keep the signatures.
"""
import asyncio


class STT:
    """Speech-to-text source."""

    async def listen(self) -> str:
        """Return the next utterance as text. Subclasses override."""
        return ""


class HandyConsoleSTT(STT):
    """Fed by /ws/console utterances (Handy pastes into the Console)."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    def feed(self, text: str) -> None:
        """Called by main.py when an utterance arrives."""
        self._queue.put_nowait(text)

    async def listen(self) -> str:
        # STUB: UI-02
        return await self._queue.get()


class WhisperSTT(STT):
    """Fallback: faster-whisper + silero-vad in the backend."""

    async def listen(self) -> str:
        # STUB: UI-05
        return "find out where Kalpana Chawla was born"


class TTS:
    """Text-to-speech output."""

    async def speak(self, text: str) -> None:
        """Say text aloud. Subclasses override."""
        return None

    def interrupt(self) -> None:
        """Stop speaking immediately. Subclasses override."""
        return None


class PiperTTS(TTS):
    async def speak(self, text: str) -> None:
        # STUB: UI-06
        return None

    def interrupt(self) -> None:
        # STUB: UI-06
        return None


class BrowserTTS(TTS):
    """Sends `speak` events; the Console voices them with speechSynthesis."""

    def __init__(self, send) -> None:
        self._send = send  # async callable taking an event dict

    async def speak(self, text: str) -> None:
        # STUB: UI-06
        await self._send({"type": "speak", "text": text})

    def interrupt(self) -> None:
        # STUB: UI-06
        return None


_COMMANDS = {"stop", "pause", "continue", "repeat", "yes", "no", "confirm",
             "back", "done", "where", "help"}


def match_command(text: str) -> str | None:
    """Map an utterance to stop|pause|continue|repeat|yes|no|confirm|back|done|where|help, else None."""
    # STUB: UI-06 (synonyms like "go back", "where am I", "what can I say")
    word = text.strip().lower().rstrip(".!?")
    return word if word in _COMMANDS else None


def spoken_digits(s: str) -> str:
    """"9876" -> "9 8 7 6"."""
    # STUB: UI-06
    return " ".join(s)


def words_to_digits(s: str) -> str:
    """"nine eight seven" -> "987"."""
    # STUB: UI-06
    words = "zero one two three four five six seven eight nine".split()
    return "".join(str(words.index(w)) for w in s.lower().split() if w in words)
