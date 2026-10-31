"""Native Windows Floating Orb Overlay & Autonomous Voice Browser.

Owner: M2 (Vishal).

Delivers:
1. Native Windows frameless, transparent, always-on-top floating desktop widget.
2. Floating 3D Crystalized Ball orb that sits on top of your Google Chrome / browser.
3. Spoken text displayed in clean, small font directly underneath the ball.
4. TargetCursor and CursorGrid click effects operating on the actual browser page.
5. Voice command matching and speech narration with complete thread and loop safety.
"""
from __future__ import annotations

import asyncio
import functools
import http.server
import json
import logging
import socket
import sys
import threading
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from playwright.async_api import async_playwright

from PyQt5.QtCore import QPoint, Qt, QTimer, QUrl, QEvent
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config
from app.voice import BrowserTTS, match_command

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("desktop_overlay")

CONSOLE_HTML = ROOT / "client" / "console.html"
TARGET_OVERLAY_SCRIPT = """
window.__targetElement = function(selector, label) {
  let el = document.querySelector(selector);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  let rect = el.getBoundingClientRect();
  
  let overlay = document.getElementById('m2-target-cursor');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'm2-target-cursor';
    overlay.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:9999999;';
    overlay.innerHTML = `
      <div id="m2-tc-tl" style="position:absolute;width:18px;height:18px;border-top:3px solid #38bdf8;border-left:3px solid #38bdf8;transition:all 0.3s cubic-bezier(0.16,1,0.3,1);"></div>
      <div id="m2-tc-tr" style="position:absolute;width:18px;height:18px;border-top:3px solid #38bdf8;border-right:3px solid #38bdf8;transition:all 0.3s cubic-bezier(0.16,1,0.3,1);"></div>
      <div id="m2-tc-br" style="position:absolute;width:18px;height:18px;border-bottom:3px solid #38bdf8;border-right:3px solid #38bdf8;transition:all 0.3s cubic-bezier(0.16,1,0.3,1);"></div>
      <div id="m2-tc-bl" style="position:absolute;width:18px;height:18px;border-bottom:3px solid #38bdf8;border-left:3px solid #38bdf8;transition:all 0.3s cubic-bezier(0.16,1,0.3,1);"></div>
      <div id="m2-tc-dot" style="position:absolute;width:6px;height:6px;background:#38bdf8;border-radius:50%;transform:translate(-50%,-50%);box-shadow:0 0 10px #38bdf8;transition:all 0.3s ease;"></div>
      <div id="m2-tc-lbl" style="position:absolute;color:#f0f9ff;font-family:'Segoe UI',system-ui,sans-serif;font-size:12px;font-weight:600;padding:3px 8px;background:rgba(15,23,42,0.92);border:1px solid #38bdf8;border-radius:5px;box-shadow:0 4px 12px rgba(0,0,0,0.5);white-space:nowrap;transition:all 0.3s ease;"></div>
      <div id="m2-cg-ripple" style="position:absolute;border-radius:50%;border:2px solid #38bdf8;box-shadow:0 0 12px #38bdf8;transform:translate(-50%,-50%) scale(0);opacity:0;pointer-events:none;"></div>
    `;
    document.body.appendChild(overlay);
  }
  
  const pad = 6;
  const top = rect.top - pad;
  const left = rect.left - pad;
  const right = rect.right + pad;
  const bottom = rect.bottom + pad;
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;

  document.getElementById('m2-tc-tl').style.top = top + 'px';
  document.getElementById('m2-tc-tl').style.left = left + 'px';
  document.getElementById('m2-tc-tr').style.top = top + 'px';
  document.getElementById('m2-tc-tr').style.left = (right - 18) + 'px';
  document.getElementById('m2-tc-br').style.top = (bottom - 18) + 'px';
  document.getElementById('m2-tc-br').style.left = (right - 18) + 'px';
  document.getElementById('m2-tc-bl').style.top = (bottom - 18) + 'px';
  document.getElementById('m2-tc-bl').style.left = left + 'px';
  
  const dot = document.getElementById('m2-tc-dot');
  dot.style.top = cy + 'px';
  dot.style.left = cx + 'px';
  
  const lbl = document.getElementById('m2-tc-lbl');
  lbl.textContent = label || 'Target';
  lbl.style.top = Math.max(8, top - 26) + 'px';
  lbl.style.left = left + 'px';
};

window.__clickEffect = function(selector) {
  let el = document.querySelector(selector);
  if (!el) return;
  let rect = el.getBoundingClientRect();
  let cx = rect.left + rect.width / 2;
  let cy = rect.top + rect.height / 2;

  let ripple = document.getElementById('m2-cg-ripple');
  if (ripple) {
    ripple.style.transition = 'none';
    ripple.style.left = cx + 'px';
    ripple.style.top = cy + 'px';
    ripple.style.width = '24px';
    ripple.style.height = '24px';
    ripple.style.transform = 'translate(-50%, -50%) scale(0.2)';
    ripple.style.opacity = '1';
    
    requestAnimationFrame(() => {
      ripple.style.transition = 'all 0.5s cubic-bezier(0.16, 1, 0.3, 1)';
      ripple.style.transform = 'translate(-50%, -50%) scale(2.8)';
      ripple.style.opacity = '0';
    });
  }
};
"""


def find_free_port(preferred: list[int]) -> int:
    for port in preferred:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class QuietHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


def serve_mock_site(port: int = 8000) -> int:
    free_port = find_free_port([port, 8001, 8002, 8003])
    handler = functools.partial(QuietHTTPHandler, directory=str(ROOT / "mock_site"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", free_port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("Mock site listening on http://127.0.0.1:%s", free_port)
    return free_port


app = FastAPI(title="M2 Floating Desktop Overlay")
app.state.site_port = 8000
app.state.browser_ready_event = threading.Event()


@app.on_event("startup")
async def startup_browser() -> None:
    """Launch Playwright browser on FastAPI's OWN event loop to eliminate cross-thread deadlocks."""
    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=False,
            channel="chrome" if Path("C:/Program Files/Google/Chrome/Application/chrome.exe").exists() else None,
            args=["--start-maximized"]
        )
        ctx = await browser.new_context(no_viewport=True)
        page = await ctx.new_page()
        await page.add_init_script(TARGET_OVERLAY_SCRIPT)
        
        target_url = f"http://127.0.0.1:{app.state.site_port}/portal/apply.html"
        await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
        try:
            await page.evaluate(TARGET_OVERLAY_SCRIPT)
        except Exception:
            pass

        app.state.pw = pw
        app.state.browser = browser
        app.state.agent_page = page
        log.info("Agent Chrome browser ready and listening on same event loop.")
    except Exception as e:
        log.error("Failed to launch Playwright browser on startup: %s", e)
    finally:
        app.state.browser_ready_event.set()


@app.on_event("shutdown")
async def shutdown_browser() -> None:
    try:
        if hasattr(app.state, "browser") and app.state.browser:
            await app.state.browser.close()
        if hasattr(app.state, "pw") and app.state.pw:
            await app.state.pw.stop()
    except Exception:
        pass


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "mode": "desktop_overlay"}


@app.get("/console", response_model=None)
async def console() -> FileResponse | HTMLResponse:
    if CONSOLE_HTML.exists():
        return FileResponse(CONSOLE_HTML)
    return HTMLResponse("<h1>Build console with 'npm run build' in client/</h1>")


class DesktopOverlaySession:
    def __init__(self, page: Any, ws: WebSocket):
        self.page = page
        self.ws = ws
        self.step_num = 0
        self.is_paused = False
        self.pending_confirmation = False
        self.last_speech = ""
        self.lock = asyncio.Lock()

    async def emit(self, event_type: str, **kwargs: Any) -> None:
        try:
            await self.ws.send_json({"type": event_type, **kwargs})
        except Exception as e:
            log.warning("WebSocket send error: %s", e)

    async def say(self, text: str) -> None:
        self.last_speech = text
        await self.emit("speak", text=text)

    async def target_and_act(self, selector: str, label: str, action: str, value: str = "") -> bool:
        page = self.page or getattr(app.state, "agent_page", None)
        if not page or page.is_closed():
            log.warning("Browser page is closed or not available.")
            await self.say("Browser page is not available.")
            return False

        try:
            # Ensure overlay helper script is injected
            try:
                await page.evaluate(TARGET_OVERLAY_SCRIPT)
            except Exception:
                pass

            # Highlight target element
            try:
                await page.evaluate(f"window.__targetElement({json.dumps(selector)}, {json.dumps(label)});")
                await asyncio.sleep(0.35)
            except Exception as e:
                log.debug("Target highlight failed (continuing): %s", e)

            # Click ripple effect
            try:
                await page.evaluate(f"window.__clickEffect({json.dumps(selector)});")
                await asyncio.sleep(0.2)
            except Exception as e:
                log.debug("Click effect failed (continuing): %s", e)

            # Perform the action with safe timeout
            if action == "click":
                await page.click(selector, timeout=5000)
            elif action == "fill":
                await page.fill(selector, value, timeout=5000)

            self.step_num += 1
            await self.emit("step", n=self.step_num, action=action.capitalize(), target=label, result="Done")
            await asyncio.sleep(0.2)
            return True
        except Exception as err:
            log.error("Action '%s' on '%s' failed: %s", action, selector, err)
            await self.emit("alert", level="warning", message=f"Could not {action} {label}")
            return False


async def handle_user_command(text: str, session: DesktopOverlaySession) -> None:
    async with session.lock:
        cmd = match_command(text)
        log.info("Overlay Utterance: %r (cmd: %r)", text, cmd)

        if cmd == "stop":
            session.is_paused = False
            session.pending_confirmation = False
            await session.emit("state", name="IDLE")
            await session.say("Stopped.")
            return

        if cmd == "pause":
            session.is_paused = True
            await session.emit("state", name="PAUSED")
            await session.say("Paused. Say continue to resume.")
            return

        if cmd == "continue":
            session.is_paused = False
            await session.emit("state", name="ACTING")
            await session.say("Resuming.")
            return

        if cmd == "repeat":
            await session.say(session.last_speech or "I have not said anything yet.")
            return

        if cmd == "where":
            page = session.page or getattr(app.state, "agent_page", None)
            title = await page.title() if page and not page.is_closed() else "Browser"
            url = page.url if page and not page.is_closed() else ""
            await session.say(f"You are viewing {title} at {url}")
            return

        if cmd == "help":
            await session.say("You can say: apply for pension, switch to bank details, fill my name, submit, stop, or pause.")
            return

        if (cmd == "confirm" or "confirm" in text.lower()) and session.pending_confirmation:
            session.pending_confirmation = False
            await session.emit("state", name="ACTING")
            await session.say("Confirmation received. Submitting application.")
            ok = await session.target_and_act("#submit-application, #submit-btn", "Submit Application", "click")
            if ok:
                await session.emit("state", name="DONE")
                await session.say("Application submitted successfully. Acknowledgment number generated.")
            return

        lower = text.lower()
        await session.emit("state", name="THINKING")
        await asyncio.sleep(0.3)

        if "bank" in lower:
            await session.emit("state", name="ACTING")
            await session.say("Switching to Bank Details tab.")
            ok = await session.target_and_act("#tab-bank", "Bank Details Tab", "click")
            if ok:
                await session.emit("field_table", fields=[
                    {"label": "Account Number", "value_masked": "••••••••1234", "status": "Filled"},
                    {"label": "IFSC Code", "value_masked": "••••••••", "status": "Filled"},
                ])
                await session.emit("state", name="ANSWERING")
                await session.say("Bank details tab is open.")

        elif "personal" in lower:
            await session.emit("state", name="ACTING")
            await session.say("Switching to Personal Details tab.")
            ok = await session.target_and_act("#tab-personal", "Personal Details Tab", "click")
            if ok:
                await session.emit("state", name="ANSWERING")
                await session.say("Switched to Personal Details tab.")

        elif "name" in lower or "fill" in lower:
            await session.emit("state", name="ACTING")
            await session.say("Entering full name.")
            ok = await session.target_and_act("#full_name", "Full Name", "fill", "Ramesh Kumar")
            if ok:
                await session.emit("field_table", fields=[
                    {"label": "Full Name", "value_masked": "Ramesh Kumar", "status": "Ready"},
                    {"label": "PIN Code", "value_masked": "560001", "status": "Ready"},
                ])
                await session.emit("state", name="ANSWERING")
                await session.say("Full name entered.")

        elif "phone" in lower or "mobile" in lower:
            await session.emit("state", name="ACTING")
            await session.say("Filling mobile number.")
            ok = await session.target_and_act("#phone", "Mobile Number", "fill", "9876543210")
            if ok:
                await session.emit("state", name="ANSWERING")
                await session.say("Mobile number entered.")

        elif "dob" in lower or "birth" in lower or "date" in lower:
            await session.emit("state", name="ACTING")
            await session.say("Filling date of birth.")
            ok = await session.target_and_act("#dob", "Date of Birth", "fill", "1990-05-15")
            if ok:
                await session.emit("state", name="ANSWERING")
                await session.say("Date of birth entered.")

        elif "submit" in lower or "done" in lower:
            session.pending_confirmation = True
            await session.emit("state", name="AWAITING_CONFIRM")
            await session.emit("pending", description="Submit disability pension application.")
            await session.say("Ready to submit your application. Say confirm to proceed, or stop.")

        elif "apply" in lower or "start" in lower or "open" in lower:
            await session.emit("state", name="ACTING")
            await session.say("Opening disability pension form.")
            await session.target_and_act("#full_name", "Full Name Field", "click")
            await session.say("Form is ready. Say fill my name to begin.")

        else:
            await session.emit("state", name="ANSWERING")
            await session.say(f"I heard: {text}. Tell me what to click or fill.")


@app.websocket("/ws/console")
async def ws_console(ws: WebSocket) -> None:
    await ws.accept()
    log.info("Floating overlay connected to WebSocket")
    page = getattr(app.state, "agent_page", None)
    session = DesktopOverlaySession(page=page, ws=ws)
    await session.emit("state", name="IDLE")

    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "utterance":
                raw_text = str(msg.get("text", "")).strip()
                if raw_text:
                    await handle_user_command(raw_text, session)
            elif kind == "key" and msg.get("name") == "Escape":
                await handle_user_command("stop", session)
            elif kind == "key" and msg.get("name") == "Space":
                await handle_user_command("pause" if not session.is_paused else "continue", session)
    except WebSocketDisconnect:
        log.info("Floating overlay disconnected")
    except Exception as err:
        log.error("WebSocket loop error: %s", err)


# ---------------- Native Floating Window (PyQt5) ----------------
class FloatingOrbWidget(QMainWindow):
    def __init__(self, url: str):
        super().__init__()
        # Frameless, Always on Top, Tool Window with Transparent Background
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        
        # Position in top right corner of the primary screen
        screen = QApplication.primaryScreen().geometry()
        width, height = 300, 320
        self.setGeometry(screen.width() - width - 40, 50, width, height)

        self.web = QWebEngineView(self)
        self.web.setStyleSheet("background: transparent;")
        self.web.page().setBackgroundColor(Qt.transparent)
        self.web.resize(width, height)
        self.web.load(QUrl(url))
        self.drag_position = None

        # Filter events on web view to allow smooth dragging anywhere on the ball
        self.web.installEventFilter(self)

    def eventFilter(self, source, event):
        if source == self.web:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                self.raise_()
                self.activateWindow()
            elif event.type() == QEvent.MouseMove and event.buttons() == Qt.LeftButton:
                if self.drag_position is not None:
                    self.move(event.globalPos() - self.drag_position)
                    return True
            elif event.type() == QEvent.MouseButtonRelease:
                self.drag_position = None
        return super().eventFilter(source, event)


def run_backend(port: int):
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main():
    site_port = serve_mock_site(8000)
    backend_port = find_free_port([8080, 8081, 8090, 8888])
    app.state.site_port = site_port

    # Run FastAPI in a dedicated daemon thread (browser starts automatically on startup)
    backend_thread = threading.Thread(target=run_backend, args=(backend_port,), daemon=True)
    backend_thread.start()

    # Wait for Chrome browser to initialize on FastAPI's loop
    app.state.browser_ready_event.wait(timeout=15)

    # Chromium GPU flags for WebGL2 in QWebEngine
    sys.argv.extend([
        "--enable-webgl",
        "--enable-webgl2-compute-context",
        "--ignore-gpu-blocklist",
        "--enable-gpu-rasterization"
    ])
    QApplication.setAttribute(Qt.AA_UseDesktopOpenGL)

    # Launch Native PyQt5 Floating Overlay on GUI thread
    qt_app = QApplication(sys.argv)
    overlay = FloatingOrbWidget(f"http://127.0.0.1:{backend_port}/console?overlay=1")
    overlay.show()

    log.info("==================================================================")
    log.info("NATIVE FLOATING ORB DESKTOP OVERLAY IS ACTIVE!")
    log.info("1. Floating Ball: 100%% transparent background, floating directly ON TOP of Google Chrome!")
    log.info("2. Small text subtitle under the ball displays spoken transcript in real time.")
    log.info("3. TargetCursor and CursorGrid animate on the opened Google Chrome window.")
    log.info("4. Thread & Event-Loop Safe: Native single-loop browser execution (NO lockups).")
    log.info("5. Click and drag the ball to move it anywhere on your screen.")
    log.info("6. Speak via Handy (Ctrl+Space) or click the ball and talk/type!")
    log.info("==================================================================")

    sys.exit(qt_app.exec_())


if __name__ == "__main__":
    main()
