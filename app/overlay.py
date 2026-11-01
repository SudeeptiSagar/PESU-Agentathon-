"""Native desktop overlay: a floating orb on top of the screen. Owner: M2 (Vishal); rewritten by M1.

This is a THIN SHELL. It only hosts the real Voice Console page (the same React orb, input box and activity panel) in a
frameless, transparent, always-on-top window, and connects to the real backend like any browser would. It contains no
agent logic, no keyword matching and no page automation: every sentence goes over /ws/console to app.agent, so the
domain policy, the held irreversible actions, the verifier and "confirm" all apply exactly as in the browser.

    python -m app.main          # the backend (the overlay waits for it)
    python -m app.overlay       # the floating orb

Handy pastes into whichever window has OS focus, so the overlay is titled config.OVERLAY_TITLE ("PESU Assistant") and the
backend's refocus_console() brings that window to the front. Needs: pip install -r requirements-overlay.txt
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from typing import Callable

from app import config

log = logging.getLogger("app.overlay")

WINDOW_SIZE = (300, 330)
MAX_SPOKEN_CHARS = 600
MARGIN = 40
# Embedded Chromium blocklists many GPUs, which turns WebGL off and the orb with it. The Console falls back to a plain
# circle either way, but with these flags most laptops get the real orb.
CHROMIUM_FLAGS = "--enable-webgl --ignore-gpu-blocklist --enable-gpu-rasterization"
WAITING_HTML = ("<html><body style='margin:0;background:transparent;color:#cbd5e1;font:15px Segoe UI,system-ui,sans-serif;"
                "display:flex;align-items:center;justify-content:center;height:100vh;text-align:center'>"
                "<div>Waiting for the assistant to start&hellip;</div></body></html>")
STATE_JS = """(() => {
  const input = document.querySelector('.capture-input');
  const c = document.createElement('canvas');
  const gl = c.getContext('webgl2') || c.getContext('webgl');
  let renderer = 'no WebGL';
  if (gl) { const i = gl.getExtension('WEBGL_debug_renderer_info');
            renderer = i ? String(gl.getParameter(i.UNMASKED_RENDERER_WEBGL)) : 'hidden'; }
  return JSON.stringify({title: document.title, input: !!input, focused: !!input && document.activeElement === input,
    orb: !!document.querySelector('canvas') ? 'webgl' : (document.querySelector('.plain-orb') ? 'plain' : 'none'),
    renderer: renderer.slice(0, 70), speech: ('speechSynthesis' in window) ? speechSynthesis.getVoices().length : -1,
    overlayClass: document.body.classList.contains('overlay-mode')});
})()"""


# ---------------------------------------------------------------- pure helpers (no Qt, unit-tested)
def base_url(host: str | None = None, port: int | None = None) -> str:
    return f"http://{host or config.HOST}:{port or config.PORT}"


def console_url(host: str | None = None, port: int | None = None) -> str:
    """The Console page, in overlay layout (transparent background, small orb)."""
    return f"{base_url(host, port)}/console?overlay=1"


def backend_ready(url: str | None = None, timeout: float = 1.0) -> bool:
    """True once the real backend answers /health."""
    try:
        with urllib.request.urlopen(f"{url or base_url()}/health", timeout=timeout) as response:
            return response.status == 200 and json.load(response).get("status") == "ok"
    except Exception:
        return False


def wait_for_backend(seconds: float, url: str | None = None, ready: Callable[..., bool] = backend_ready,
                     sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> bool:
    """Poll the backend until it is ready or `seconds` have passed."""
    deadline = clock() + seconds
    while True:
        if ready(url):
            return True
        if clock() >= deadline:
            return False
        sleep(0.5)


# ---------------------------------------------------------------- speech (the embedded browser has no speechSynthesis)
SPEAK_PREFIX = "PESU_SPEAK:"
CANCEL_MESSAGE = "PESU_CANCEL_SPEECH"
# One long-lived PowerShell speaks with Windows' built-in voices, so there is nothing to install and every line is queued.
# stdin lines: "SPEAK <text>" queues a line, "CANCEL" stops everything now. With PESU_SPEECH_NULL=1 (tests) the audio goes
# nowhere and each finished line is acknowledged on stdout.
SPEECH_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$quiet = ($env:PESU_SPEECH_NULL -eq '1')
if ($quiet) { $s.SetOutputToNull() }
$n = 0
while ($true) {
  $line = [Console]::In.ReadLine()
  if ($line -eq $null) { break }
  if ($line -eq 'CANCEL') { $s.SpeakAsyncCancelAll(); continue }
  if ($line.StartsWith('SPEAK ')) {
    $text = $line.Substring(6)
    if ($quiet) { $s.Speak($text); $n++; [Console]::Out.WriteLine("spoken $n"); [Console]::Out.Flush() }
    else { [void]$s.SpeakAsync($text) }
  }
}
"""


def clean_speech(text: object) -> str:
    """One line of plain text, at most MAX_SPOKEN_CHARS, with control characters removed. Empty if nothing is left."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text))
    return re.sub(r"\s+", " ", text).strip()[:MAX_SPOKEN_CHARS]


class WindowsSpeech:
    """Speaks lines with Windows' built-in voices through one PowerShell process, started on the first line."""

    def __init__(self, popen: Callable[..., subprocess.Popen] = subprocess.Popen) -> None:
        self._popen = popen
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self.acks: list[str] = []          # "spoken N" lines, only in the silent test mode

    def _start(self) -> subprocess.Popen | None:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        encoded = base64.b64encode(SPEECH_SCRIPT.encode("utf-16-le")).decode("ascii")
        try:
            self._proc = self._popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as e:
            log.warning("speech is unavailable: %s", type(e).__name__)
            self._proc = None
            return None
        threading.Thread(target=self._read_acks, args=(self._proc,), daemon=True).start()
        return self._proc

    def _read_acks(self, proc) -> None:
        try:
            for raw in proc.stdout:
                self.acks.append(raw.decode("utf-8", "replace").strip())
        except Exception:
            pass

    def _send(self, line: str) -> None:
        with self._lock:
            proc = self._start()
            if proc is None or proc.stdin is None:
                return
            try:
                proc.stdin.write((line + "\n").encode("utf-8"))
                proc.stdin.flush()
            except (OSError, ValueError):
                self._proc = None          # it died; the next line starts a fresh one

    def speak(self, text: object) -> None:
        cleaned = clean_speech(text)
        if cleaned:
            self._send("SPEAK " + cleaned)

    def cancel(self) -> None:
        if self._proc is not None:         # nothing is speaking if nothing was ever started
            self._send("CANCEL")

    def close(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.stdin.close()
                proc.wait(3)
            except Exception:
                proc.kill()


# Natural voice: Microsoft neural voices through edge-tts (needs internet), played with Windows MCI. OVERLAY_VOICE=windows
# keeps the built-in voice. Any voice from `python -m edge_tts --list-voices` works for TTS_VOICE.
NEURAL_VOICE = os.getenv("TTS_VOICE", "").strip() or "en-US-AvaMultilingualNeural"
NEURAL_RATE = os.getenv("TTS_RATE", "").strip() or "+0%"
NEURAL_TIMEOUT = 6.0
NEURAL_PARALLEL = 2           # more parallel requests get throttled, and throttled lines fell back mid-sentence
NEURAL_COOLDOWN = 60.0        # after repeated failures, stay on the built-in voice this long instead of switching per line
_MCI_ALIAS = "pesu_tts"


class _CoolingDown(Exception):
    """The neural voice failed recently; this line uses the built-in voice."""


class NeuralSpeech:
    """Speaks with a natural neural voice. Lines are synthesized ahead and played in order; repeated lines come from a
    cache. A line that cannot be synthesized in time is spoken by the built-in voice in the same queue, so speech never
    goes silent and two voices never overlap.
    """

    def __init__(self, fallback: WindowsSpeech | None = None) -> None:
        import asyncio
        import itertools
        import queue
        import tempfile

        self._fallback = fallback or WindowsSpeech()
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True, name="tts-synth").start()
        self._order: queue.Queue = queue.Queue()
        self._generation = 0
        self._cache: dict[str, str] = {}
        self._names = itertools.count()
        self._dir = tempfile.mkdtemp(prefix="pesu-tts-")
        self._limit = asyncio.Semaphore(NEURAL_PARALLEL)
        self._failures = 0
        self._neural_after = 0.0          # monotonic time before which lines use the built-in voice
        threading.Thread(target=self._play_loop, daemon=True, name="tts-play").start()

    @property
    def acks(self) -> list[str]:
        return self._fallback.acks

    def speak(self, text: object) -> None:
        import asyncio

        cleaned = clean_speech(text)
        if cleaned:
            future = asyncio.run_coroutine_threadsafe(self._synthesize(cleaned), self._loop)
            self._order.put((self._generation, cleaned, future))

    async def _synthesize(self, text: str) -> str:
        import asyncio

        import edge_tts

        cached = self._cache.get(text)
        if cached and os.path.exists(cached):
            return cached
        if time.monotonic() < self._neural_after:
            raise _CoolingDown
        async with self._limit:
            path = os.path.join(self._dir, f"line{next(self._names)}.mp3")
            await asyncio.wait_for(edge_tts.Communicate(text, NEURAL_VOICE, rate=NEURAL_RATE).save(path),
                                   NEURAL_TIMEOUT)
        self._cache[text] = path
        return path

    def _builtin_voice(self):
        """SAPI in the player thread, so the built-in voice is queued with the neural lines. None without pywin32."""
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            return win32com.client.Dispatch("SAPI.SpVoice")
        except Exception as e:
            log.warning("built-in voice is not available in the queue: %s", type(e).__name__)
            return None

    def _speak_builtin(self, sapi, text: str, generation: int) -> None:
        if sapi is None:
            self._fallback.speak(text)     # last resort; may overlap, but never silent
            return
        try:
            sapi.Speak(text, 1)            # SVSFlagsAsync: return now, poll so cancel can cut it short
            while generation == self._generation:
                if sapi.WaitUntilDone(30):
                    return
            sapi.Speak("", 3)              # async + purge: stop the current line
        except Exception as e:
            log.warning("built-in voice failed: %s", type(e).__name__)

    def _play_loop(self) -> None:
        import ctypes

        mci = ctypes.windll.winmm.mciSendStringW
        status = ctypes.create_unicode_buffer(64)
        sapi = self._builtin_voice()
        while True:
            item = self._order.get()
            if item is None:
                return
            generation, text, future = item
            if generation != self._generation:
                continue                   # cancelled while waiting
            try:
                # Lines wait for earlier ones to synthesize (NEURAL_PARALLEL), so allow for the queue ahead of this one.
                path = future.result(NEURAL_TIMEOUT * 4)
                self._failures = 0
            except Exception as e:
                log.warning("neural voice unavailable for one line: %s", type(e).__name__)
                path = None
                if not isinstance(e, _CoolingDown):
                    self._failures += 1
                    if self._failures >= 2:
                        self._neural_after = time.monotonic() + NEURAL_COOLDOWN
                        self._failures = 0
            if generation != self._generation:
                continue
            if path is None or mci(f'open "{path}" type mpegvideo alias {_MCI_ALIAS}', None, 0, None) != 0:
                self._speak_builtin(sapi, text, generation)
                continue
            log.debug("neural line starts")
            try:
                mci(f"play {_MCI_ALIAS}", None, 0, None)
                while generation == self._generation:
                    mci(f"status {_MCI_ALIAS} mode", status, 64, None)
                    if status.value != "playing":
                        break
                    time.sleep(0.03)
            finally:
                mci(f"stop {_MCI_ALIAS}", None, 0, None)
                mci(f"close {_MCI_ALIAS}", None, 0, None)
                log.debug("neural line ends")

    def cancel(self) -> None:
        self._generation += 1              # the player drops queued lines and stops the current one within 30 ms
        self._fallback.cancel()

    def close(self) -> None:
        self.cancel()
        self._order.put(None)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._fallback.close()


class NoSpeech:
    """Other platforms: the overlay is Windows-first; the browser Console speaks there."""

    acks: list[str] = []

    def speak(self, text: object) -> None:
        log.warning("speech is only built in for Windows; the overlay stays silent")

    def cancel(self) -> None:
        pass

    def close(self) -> None:
        pass


def make_speech():
    if sys.platform != "win32":
        return NoSpeech()
    # Tests (PESU_SPEECH_NULL) and OVERLAY_VOICE=windows keep the built-in voice.
    if os.getenv("PESU_SPEECH_NULL") != "1" and (os.getenv("OVERLAY_VOICE", "").strip().lower() or "neural") == "neural":
        try:
            import edge_tts  # noqa: F401
            return NeuralSpeech()
        except ImportError:
            log.warning("edge-tts is not installed; using the built-in Windows voice")
    return WindowsSpeech()


def handle_console_message(message: str, speech) -> bool:
    """The Console reports speech through console.info. Returns True if the message was a speech message."""
    if message.startswith(SPEAK_PREFIX):
        try:
            speech.speak(json.loads(message[len(SPEAK_PREFIX):]))
        except ValueError:
            pass
        return True
    if message == CANCEL_MESSAGE:
        speech.cancel()
        return True
    return False


# ---------------------------------------------------------------- the Qt window
def _qt():
    try:
        from PyQt5.QtCore import QEvent, QPoint, Qt, QTimer, QUrl
        from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineView
        from PyQt5.QtWidgets import QApplication, QMainWindow, QMenu
    except ImportError as e:
        raise SystemExit("The desktop overlay needs PyQt5 and PyQtWebEngine: pip install -r requirements-overlay.txt "
                         f"({e})") from None
    return QEvent, QPoint, Qt, QTimer, QUrl, QWebEnginePage, QWebEngineView, QApplication, QMainWindow, QMenu


def run(url: str | None = None, smoke: float = 0.0, on_top: bool = True) -> int:
    """Open the overlay. With smoke > 0: load the page, print one JSON line about it after `smoke` seconds, and exit."""
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " " + CHROMIUM_FLAGS).strip()
    QEvent, QPoint, Qt, QTimer, QUrl, QWebEnginePage, QWebEngineView, QApplication, QMainWindow, QMenu = _qt()
    target = url or console_url()
    health_base = target.split("/console")[0]

    speech = make_speech()

    class ConsolePage(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            if not handle_console_message(message, speech):
                log.debug("console: %s", message[:120])

    class Overlay(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            flags = Qt.Window | Qt.FramelessWindowHint | (Qt.WindowStaysOnTopHint if on_top else Qt.Window)
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setStyleSheet("background: transparent;")
            self.setWindowTitle(config.OVERLAY_TITLE)
            screen = QApplication.primaryScreen().availableGeometry()
            width, height = WINDOW_SIZE
            self.setGeometry(screen.right() - width - MARGIN, screen.bottom() - height - MARGIN, width, height)

            self.web = QWebEngineView(self)
            self.web.setPage(ConsolePage(self.web))
            self.web.setStyleSheet("background: transparent;")
            self.web.page().setBackgroundColor(Qt.transparent)
            self.web.resize(width, height)
            self.web.setHtml(WAITING_HTML)
            self.web.installEventFilter(self)
            self.web.loadFinished.connect(self.focus_input)
            self.drag_from = None
            self.loaded = False
            self.poll = QTimer(self)
            self.poll.timeout.connect(self.check_backend)
            self.poll.start(800)

        def check_backend(self) -> None:
            """Load the Console once the backend answers; until then the waiting message stays."""
            if not self.loaded and backend_ready(health_base, timeout=0.4):
                self.loaded = True
                self.poll.stop()
                self.web.load(QUrl(target))

        def focus_input(self, *_) -> None:
            """Put the keyboard focus in the Console's input box: Handy pastes into it."""
            if self.loaded:
                self.web.setFocus()
                self.web.page().runJavaScript("document.querySelector('.capture-input') && document.querySelector('.capture-input').focus();")

        def bring_forward(self) -> None:
            self.raise_()
            self.activateWindow()
            self.focus_input()

        def changeEvent(self, event) -> None:
            if event.type() == QEvent.ActivationChange and self.isActiveWindow():
                self.focus_input()
            super().changeEvent(event)

        def enterEvent(self, event) -> None:
            self.bring_forward()
            super().enterEvent(event)

        def show_menu(self, pos) -> None:
            menu = QMenu(self)
            menu.setStyleSheet("QMenu{background:#0f172a;color:#f8fafc;border:1px solid #475569;border-radius:8px;padding:4px;"
                               "font:13px 'Segoe UI',sans-serif} QMenu::item{padding:6px 18px;border-radius:4px}"
                               "QMenu::item:selected{background:#2563eb}")
            top = menu.addAction("Always on top")
            top.setCheckable(True)
            top.setChecked(bool(self.windowFlags() & Qt.WindowStaysOnTopHint))
            reload_ = menu.addAction("Reload the Console")
            quit_ = menu.addAction("Close the assistant")
            chosen = menu.exec_(pos)
            if chosen is top:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, top.isChecked())
                self.show()
                self.bring_forward()
            elif chosen is reload_:
                self.web.load(QUrl(target))
            elif chosen is quit_:
                QApplication.quit()

        def eventFilter(self, source, event):
            if source is self.web:
                kind = event.type()
                if kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                    self.drag_from = event.globalPos() - self.frameGeometry().topLeft()
                    self.bring_forward()
                elif kind == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
                    self.show_menu(event.globalPos())
                    return True
                elif kind == QEvent.MouseMove and event.buttons() == Qt.LeftButton and self.drag_from is not None:
                    self.move(event.globalPos() - self.drag_from)
                    return True
                elif kind == QEvent.MouseButtonRelease:
                    self.drag_from = None
            return super().eventFilter(source, event)

    app = QApplication(sys.argv[:1])
    window = Overlay()
    window.show()
    window.bring_forward()
    if smoke:
        report: dict = {}

        def collect() -> None:
            # speak one line through the same path the Console uses, then give the speech process time to acknowledge it
            window.web.page().runJavaScript("console.info('PESU_SPEAK:' + JSON.stringify('Overlay speech check'));")
            QTimer.singleShot(2500, lambda: window.web.page().runJavaScript(STATE_JS, finish))

        def finish(result) -> None:
            report["state"] = json.loads(result) if result else None
            print(json.dumps({"title": window.windowTitle(), "loaded": window.loaded, "page": report["state"],
                              "speech_acks": list(speech.acks)}), flush=True)
            QApplication.quit()

        QTimer.singleShot(int(smoke * 1000), collect)
    code = app.exec_()
    speech.close()
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", help="Console URL (default: the backend from .env, in overlay layout)")
    ap.add_argument("--no-topmost", action="store_true", help="do not keep the window above others")
    ap.add_argument("--smoke", type=float, default=0.0, metavar="SECONDS",
                    help="load the page, print one JSON line about it after SECONDS and exit (diagnostics, tests)")
    args = ap.parse_args()
    return run(url=args.url, smoke=args.smoke, on_top=not args.no_topmost)


if __name__ == "__main__":
    sys.exit(main())
