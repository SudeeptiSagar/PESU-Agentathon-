"""Speech input and output, command matcher, digit helpers (PRD Sections 8 and 12).

Owner: M2 (Vishal). CORE-01 contract stubs; replace the bodies, keep the signatures.
"""
import asyncio
import re
import threading
from contextlib import suppress
from pathlib import Path

from app import config


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
    """Local Piper speech output with stop support.

    Piper and sounddevice are imported only when speech is requested so a
    browser-TTS configuration does not need either optional dependency.
    """

    _initialization_lock = threading.Lock()

    def _ensure_state(self) -> None:
        if hasattr(self, "_state_lock"):
            return
        with self._initialization_lock:
            if not hasattr(self, "_state_lock"):
                self._voice = None
                self._sounddevice = None
                self._load_lock = threading.Lock()
                self._state_lock = threading.Lock()
                self._speak_lock = asyncio.Lock()
                self._stop_event: threading.Event | None = None
                self._stream = None

    async def speak(self, text: str) -> None:
        if not text or not text.strip():
            return
        self._ensure_state()

        # A new utterance replaces current playback. Piper synthesis and audio
        # writes are blocking, so keep them off the WebSocket event loop.
        self.interrupt()
        async with self._speak_lock:
            stop_event = threading.Event()
            with self._state_lock:
                self._stop_event = stop_event
            try:
                await asyncio.to_thread(self._speak_sync, text, stop_event)
            finally:
                stop_event.set()
                self._abort_stream(stop_event)
                with self._state_lock:
                    if self._stop_event is stop_event:
                        self._stop_event = None

    def interrupt(self) -> None:
        self._ensure_state()
        with self._state_lock:
            stop_event = self._stop_event
        if stop_event is not None:
            stop_event.set()
            self._abort_stream(stop_event)

    def _load_voice(self):
        self._ensure_state()
        if self._voice is not None and self._sounddevice is not None:
            return self._voice, self._sounddevice

        with self._load_lock:
            if self._voice is not None and self._sounddevice is not None:
                return self._voice, self._sounddevice

            model_path = Path(config.PIPER_VOICE).expanduser() if config.PIPER_VOICE else None
            if model_path is None:
                raise RuntimeError(
                    "Piper TTS needs PIPER_VOICE to point to a downloaded .onnx voice model; "
                    "use TTS_BACKEND=browser for Console speech instead."
                )
            if not model_path.is_file():
                raise RuntimeError(f"Piper voice model was not found: {model_path}")

            try:
                from piper import PiperVoice
            except ImportError as exc:
                raise RuntimeError(
                    "Piper TTS is not installed. Install piper-tts and set PIPER_VOICE."
                ) from exc
            try:
                import sounddevice
            except ImportError as exc:
                raise RuntimeError(
                    "Piper audio playback needs the optional sounddevice package."
                ) from exc

            self._voice = PiperVoice.load(str(model_path))
            self._sounddevice = sounddevice
            return self._voice, self._sounddevice

    def _speak_sync(self, text: str, stop_event: threading.Event) -> None:
        voice, sounddevice = self._load_voice()
        stream = None
        audio_format = None
        try:
            for chunk in voice.synthesize(text):
                if stop_event.is_set():
                    break

                if chunk.sample_width != 2:
                    raise RuntimeError(
                        f"Piper returned unsupported audio sample width: {chunk.sample_width}"
                    )
                dtype = "int16"
                chunk_format = (chunk.sample_rate, chunk.sample_channels, dtype)
                if stream is None:
                    stream = sounddevice.RawOutputStream(
                        samplerate=chunk.sample_rate,
                        channels=chunk.sample_channels,
                        dtype=dtype,
                    )
                    with self._state_lock:
                        if stop_event.is_set():
                            break
                        self._stream = stream
                    stream.start()
                    audio_format = chunk_format
                elif chunk_format != audio_format:
                    raise RuntimeError("Piper changed audio format during one utterance")

                if not stop_event.is_set():
                    stream.write(chunk.audio_int16_bytes)
        finally:
            if stream is not None:
                with self._state_lock:
                    if self._stream is stream:
                        self._stream = None
                if stop_event.is_set():
                    with suppress(Exception):
                        stream.abort()
                else:
                    with suppress(Exception):
                        stream.stop()
                with suppress(Exception):
                    stream.close()

    def _abort_stream(self, stop_event: threading.Event) -> None:
        with self._state_lock:
            stream = self._stream if self._stop_event is stop_event else None
        if stream is not None:
            with suppress(Exception):
                stream.abort()


class BrowserTTS(TTS):
    """Sends `speak` events; the Console voices them with speechSynthesis."""

    def __init__(self, send) -> None:
        self._send = send  # async callable taking an event dict

    async def speak(self, text: str) -> None:
        await self._send({"type": "speak", "text": text})

    def interrupt(self) -> None:
        """Browser speech is cancelled by the Console on new input or Escape.

        Section 12 has no backend-to-browser cancellation event, so this
        adapter intentionally has no backend-side interrupt operation.
        """
        return None


def match_command(text: str) -> str | None:
    """Map an utterance to stop|pause|continue|repeat|yes|no|confirm|back|done|where|help, else None."""
    normalized = text.casefold().replace("’", "'")
    normalized = re.sub(r"(?<=\w)'(?=\w)", "", normalized)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    phrase = " ".join(normalized.split())
    return _COMMAND_ALIASES.get(phrase)


def spoken_digits(s: str) -> str:
    """"9876" -> "9 8 7 6"."""
    return re.sub(r"\d+", lambda match: " ".join(match.group()), s)


def words_to_digits(s: str) -> str:
    """"nine eight seven" -> "987"."""
    digit_words = {
        "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3",
        "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
        "nine": "9",
    }
    alternatives = "|".join(digit_words)
    sequence = re.compile(
        rf"(?<!\w)(?:{alternatives})(?:[\s,-]+(?:{alternatives}))*(?!\w)",
        re.IGNORECASE,
    )

    def replace_sequence(match: re.Match[str]) -> str:
        words = re.findall(r"[a-z]+", match.group(), re.IGNORECASE)
        return "".join(digit_words[word.casefold()] for word in words)

    return sequence.sub(replace_sequence, s)


_COMMAND_ALIASES = {
    "stop": "stop", "stop now": "stop", "halt": "stop", "cancel": "stop",
    "cancel that": "stop", "cancel task": "stop",
    "pause": "pause", "pause now": "pause", "wait": "pause", "hold on": "pause",
    "continue": "continue", "resume": "continue", "carry on": "continue",
    "keep going": "continue", "go on": "continue", "unpause": "continue",
    "repeat": "repeat", "repeat that": "repeat", "say that again": "repeat",
    "say it again": "repeat", "again please": "repeat",
    "yes": "yes", "yeah": "yes", "yep": "yes", "yup": "yes",
    "no": "no", "nope": "no", "nah": "no",
    "confirm": "confirm", "confirm it": "confirm", "confirm this": "confirm",
    "back": "back", "go back": "back", "return": "back",
    "previous page": "back", "go to previous page": "back",
    "done": "done", "all done": "done", "finished": "done", "im done": "done",
    "thats all": "done",
    "where": "where", "where am i": "where", "where am i now": "where",
    "where are we": "where", "where are you": "where", "what page am i on": "where",
    "what page is this": "where",
    "help": "help", "help me": "help", "what can i say": "help",
    "what can you do": "help", "available commands": "help", "list commands": "help",
}
