"""Unit tests for the voice module's text helpers and event adapters."""
import asyncio
import threading
from types import SimpleNamespace

import pytest

from app.voice import BrowserTTS, PiperTTS, match_command, spoken_digits, words_to_digits


@pytest.mark.parametrize(
    ("utterance", "expected"),
    [
        ("STOP!", "stop"),
        ("cancel that", "stop"),
        ("hold on", "pause"),
        ("resume", "continue"),
        ("say that again", "repeat"),
        ("Yep.", "yes"),
        ("nope", "no"),
        ("confirm it", "confirm"),
        ("go back", "back"),
        ("I'm done", "done"),
        ("Where am I?", "where"),
        ("What can I say?", "help"),
    ],
)
def test_match_command_covers_section_12_commands(utterance, expected):
    assert match_command(utterance) == expected


@pytest.mark.parametrize(
    "utterance", ["", "please stop the timer", "I don't know", "helpful", "confirm later"]
)
def test_match_command_requires_a_standalone_command_phrase(utterance):
    assert match_command(utterance) is None

@pytest.mark.parametrize("utterance", ["proceed", "approve", "yes", "ok", "go ahead"])
def test_match_command_never_maps_non_confirm_words_to_confirm(utterance):
    result = match_command(utterance)
    assert result != "confirm"
    assert result in (None, "yes")



def test_spoken_digits_separates_digit_runs_and_preserves_other_text():
    assert spoken_digits("Phone 9876, PIN 04") == "Phone 9 8 7 6, PIN 0 4"
    assert spoken_digits("no number here") == "no number here"


def test_words_to_digits_converts_digit_sequences_and_preserves_surrounding_words():
    assert words_to_digits("nine eight seven") == "987"
    assert words_to_digits("Call me at Nine, eight, seven.") == "Call me at 987."
    assert words_to_digits("oh-five, zero") == "050"
    assert words_to_digits("someone said one hundred") == "someone said 1 hundred"


def test_browser_tts_sends_the_section_12_speak_event():
    events = []

    async def send(event):
        events.append(event)

    asyncio.run(BrowserTTS(send).speak("Hello there"))
    assert events == [{"type": "speak", "text": "Hello there"}]


class _FakeStream:
    def __init__(self, *, started=None, release=None, **kwargs):
        self.kwargs = kwargs
        self.started_event = started
        self.release_event = release
        self.written = []
        self.aborted = False
        self.stopped = False
        self.closed = False

    def start(self):
        pass

    def write(self, audio):
        self.written.append(audio)
        if self.started_event is not None:
            self.started_event.set()
        if self.release_event is not None:
            self.release_event.wait(timeout=2)

    def abort(self):
        self.aborted = True
        if self.release_event is not None:
            self.release_event.set()

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


def _fake_voice():
    chunk = SimpleNamespace(
        sample_rate=22050,
        sample_width=2,
        sample_channels=1,
        audio_int16_bytes=b"\x00\x00",
    )

    class Voice:
        def synthesize(self, text):
            assert text == "Hello there"
            return [chunk]

    return Voice()


def test_piper_streams_audio_and_closes_the_output(monkeypatch):
    streams = []

    def create_stream(**kwargs):
        stream = _FakeStream(**kwargs)
        streams.append(stream)
        return stream

    tts = PiperTTS()
    monkeypatch.setattr(tts, "_load_voice", lambda: (_fake_voice(), SimpleNamespace(RawOutputStream=create_stream)))

    asyncio.run(tts.speak("Hello there"))

    assert streams[0].kwargs == {"samplerate": 22050, "channels": 1, "dtype": "int16"}
    assert streams[0].written == [b"\x00\x00"]
    assert streams[0].stopped
    assert streams[0].closed


def test_piper_interrupt_aborts_active_audio(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    streams = []

    def create_stream(**kwargs):
        stream = _FakeStream(started=started, release=release, **kwargs)
        streams.append(stream)
        return stream

    tts = PiperTTS()
    monkeypatch.setattr(tts, "_load_voice", lambda: (_fake_voice(), SimpleNamespace(RawOutputStream=create_stream)))

    async def run():
        speech = asyncio.create_task(tts.speak("Hello there"))
        assert await asyncio.to_thread(started.wait, timeout=2)
        tts.interrupt()
        await asyncio.wait_for(speech, timeout=2)

    asyncio.run(run())

    assert streams[0].aborted
    assert streams[0].closed
