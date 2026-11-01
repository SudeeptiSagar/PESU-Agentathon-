"""app/overlay.py: the pure helpers, the Windows speech bridge protocol, and a real silent-PowerShell round trip."""
import io
import json
import sys
import time

import pytest

from app import config, overlay


class FakeProc:
    def __init__(self):
        self.stdin, self.stdout, self.dead = io.BytesIO(), io.BytesIO(), False

    def poll(self):
        return 0 if self.dead else None

    def wait(self, t=None):
        return 0

    def kill(self):
        self.dead = True


def fake_speech():
    procs = []

    def popen(*a, **k):
        procs.append(FakeProc())
        return procs[-1]
    return overlay.WindowsSpeech(popen=popen), procs


def test_urls_follow_the_configured_host_and_port(monkeypatch):
    monkeypatch.setattr(config, "HOST", "127.0.0.1"); monkeypatch.setattr(config, "PORT", 9123)
    assert overlay.base_url() == "http://127.0.0.1:9123"
    assert overlay.console_url() == "http://127.0.0.1:9123/console?overlay=1"


def test_wait_for_backend_succeeds_when_it_comes_up_and_times_out_when_not():
    t = [0.0]
    calls = []
    assert overlay.wait_for_backend(5, ready=lambda u: calls.append(1) or len(calls) == 3,
                                    sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])
    t[0] = 0.0
    assert not overlay.wait_for_backend(2, ready=lambda u: False, sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])


def test_backend_ready_is_false_when_nothing_listens():
    assert overlay.backend_ready("http://127.0.0.1:1", timeout=0.2) is False


def test_clean_speech_strips_control_characters_and_limits_length():
    assert overlay.clean_speech("hello\r\nworld\x00 !") == "hello world !"
    assert len(overlay.clean_speech("a" * 100000)) == overlay.MAX_SPOKEN_CHARS
    assert overlay.clean_speech("\n\t ") == ""


def test_speak_sends_one_line_and_starts_the_process_once():
    speech, procs = fake_speech()
    speech.speak("one\ntwo"); speech.speak("three")
    assert len(procs) == 1
    assert procs[0].stdin.getvalue() == b"SPEAK one two\nSPEAK three\n"


def test_empty_text_is_not_sent_and_cancel_before_any_speech_starts_nothing():
    speech, procs = fake_speech()
    speech.speak("  "); speech.cancel()
    assert procs == []
    speech.speak("hi"); speech.cancel()
    assert procs[0].stdin.getvalue() == b"SPEAK hi\nCANCEL\n"


def test_a_dead_process_is_replaced_on_the_next_line():
    speech, procs = fake_speech()
    speech.speak("a"); procs[0].dead = True; speech.speak("b")
    assert len(procs) == 2 and procs[1].stdin.getvalue() == b"SPEAK b\n"


def test_a_missing_powershell_is_survived():
    def popen(*a, **k):
        raise FileNotFoundError("powershell")
    overlay.WindowsSpeech(popen=popen).speak("hello")      # no exception


class Recorder:
    def __init__(self): self.said, self.cancelled = [], 0
    def speak(self, t): self.said.append(t)
    def cancel(self): self.cancelled += 1


def test_console_messages_are_routed_and_others_ignored():
    r = Recorder()
    assert overlay.handle_console_message("PESU_SPEAK:" + json.dumps("Hello there"), r)
    assert overlay.handle_console_message("PESU_CANCEL_SPEECH", r)
    assert not overlay.handle_console_message("some page log", r)
    assert overlay.handle_console_message("PESU_SPEAK:{not json", r)
    assert r.said == ["Hello there"] and r.cancelled == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows speech")
def test_real_powershell_speaks_silently_and_acknowledges(monkeypatch):
    monkeypatch.setenv("PESU_SPEECH_NULL", "1")
    speech = overlay.WindowsSpeech()
    try:
        speech.speak("Testing the speech bridge.")
        for _ in range(100):
            if speech.acks == ["spoken 1"]:
                break
            time.sleep(0.1)
        assert speech.acks == ["spoken 1"]
    finally:
        speech.close()
