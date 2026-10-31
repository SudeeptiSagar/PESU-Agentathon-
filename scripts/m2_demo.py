"""M2 Voice Console MVP Demonstration & Test Harness.

Owner: M2 (Vishal).
Launches:
1. Mock test website (mock_site/) on http://127.0.0.1:8000
2. FastAPI Voice Console backend on http://127.0.0.1:8080
3. Playwright headed Chromium BrowserController side-by-side:
   - Left window: Voice Console with Crystalized Ball orb
   - Right window: Agent Browser with live TargetCursor and CursorGrid click feedback
4. Routes Handy transcripts / Console inputs, executes real browser steps, and narrates progress.
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config
from app.browser import BrowserController
from app.voice import BrowserTTS, match_command

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("m2_demo")

CONSOLE_HTML = ROOT / "client" / "console.html"


def find_free_port(candidates: list[int]) -> int:
    for port in candidates:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return candidates[0]
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
      <div id="m2-tc-tl" style="position:absolute;width:16px;height:16px;border-top:3px solid #38bdf8;border-left:3px solid #38bdf8;transition:all 0.3s cubic-bezier(0.16,1,0.3,1);"></div>
      <div id="m2-tc-tr" style="position:absolute;width:16px;height:16px;border-top:3px solid #38bdf8;border-right:3px solid #38bdf8;transition:all 0.3s cubic-bezier(0.16,1,0.3,1);"></div>
      <div id="m2-tc-br" style="position:absolute;width:16px;height:16px;border-bottom:3px solid #38bdf8;border-right:3px solid #38bdf8;transition:all 0.3s cubic-bezier(0.16,1,0.3,1);"></div>
      <div id="m2-tc-bl" style="position:absolute;width:16px;height:16px;border-bottom:3px solid #38bdf8;border-left:3px solid #38bdf8;transition:all 0.3s cubic-bezier(0.16,1,0.3,1);"></div>
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
  document.getElementById('m2-tc-tr').style.left = (right - 16) + 'px';
  document.getElementById('m2-tc-br').style.top = (bottom - 16) + 'px';
  document.getElementById('m2-tc-br').style.left = (right - 16) + 'px';
  document.getElementById('m2-tc-bl').style.top = (bottom - 16) + 'px';
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
    ripple.style.top = cy + 'px';
    ripple.style.left = cx + 'px';
    ripple.style.width = '24px';
    ripple.style.height = '24px';
    ripple.style.transform = 'translate(-50%,-50%) scale(1)';
    ripple.style.opacity = '1';
    
    requestAnimationFrame(() => {
      ripple.style.transition = 'transform 0.45s cubic-bezier(0,0,0.2,1), opacity 0.45s ease-out';
      ripple.style.transform = 'translate(-50%,-50%) scale(4.5)';
      ripple.style.opacity = '0';
    });
  }
};
"""


class QuietHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


def serve_mock_site(port: int = 8000) -> int:
    free_port = find_free_port([port, 8001, 8002])
    handler = functools.partial(QuietHTTPHandler, directory=str(ROOT / "mock_site"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", free_port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("Mock site server listening on http://127.0.0.1:%s", free_port)
    return free_port


app = FastAPI(title="M2 Voice Browser MVP")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "mode": "m2_demo"}


@app.get("/console", response_model=None)
async def console() -> FileResponse | HTMLResponse:
    if CONSOLE_HTML.exists():
        return FileResponse(CONSOLE_HTML)
    return HTMLResponse("<h1>Build console with 'npm run build' in client/</h1>")


class M2HarnessSession:
    def __init__(self, browser: BrowserController, ws: WebSocket):
        self.browser = browser
        self.ws = ws
        self.step_num = 0
        self.is_paused = False
        self.pending_confirmation = False
        self.last_speech = ""

    async def emit(self, event_type: str, **kwargs: Any) -> None:
        await self.ws.send_json({"type": event_type, **kwargs})

    async def say(self, text: str) -> None:
        self.last_speech = text
        await self.emit("speak", text=text)

    async def target_and_act(self, selector: str, label: str, action: str, value: str = "") -> None:
        if self.browser.active is None:
            return
        page = self.browser.active

        # Visual TargetCursor overlay
        try:
            await page.evaluate(f"window.__targetElement({json.dumps(selector)}, {json.dumps(label)});")
            await asyncio.sleep(0.4)
        except Exception:
            pass

        # Visual CursorGrid click ripple
        try:
            await page.evaluate(f"window.__clickEffect({json.dumps(selector)});")
            await asyncio.sleep(0.2)
        except Exception:
            pass

        # Real DOM action
        if action == "click":
            await page.click(selector, timeout=3000)
        elif action == "fill":
            await page.fill(selector, value, timeout=3000)

        self.step_num += 1
        await self.emit("step", n=self.step_num, action=action.capitalize(), target=label, result="Done")
        await asyncio.sleep(0.3)


async def handle_user_command(text: str, session: M2HarnessSession) -> None:
    cmd = match_command(text)
    log.info("Utterance received: %r (matched command: %r)", text, cmd)

    if cmd == "stop":
        session.is_paused = False
        session.pending_confirmation = False
        await session.emit("state", name="IDLE")
        await session.say("Stopped.")
        await session.browser.refocus_console()
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
        title = await session.browser.active.title() if session.browser.active else "Browser"
        url = session.browser.active.url if session.browser.active else ""
        await session.say(f"You are viewing {title} at {url}")
        return

    if cmd == "help":
        await session.say(
            "You can say: apply for pension, switch to bank details, fill my name, submit application, stop, or pause."
        )
        return

    if cmd == "confirm" and session.pending_confirmation:
        session.pending_confirmation = False
        await session.emit("state", name="ACTING")
        await session.say("Confirmation received. Submitting application.")
        await session.target_and_act("#submit-btn", "Submit Application", "click")
        await session.emit("state", name="DONE")
        await session.say("Application submitted successfully. Acknowledgment number generated.")
        await session.browser.refocus_console()
        return

    # Task Execution Workflow:
    lower = text.lower()
    await session.emit("state", name="THINKING")
    await asyncio.sleep(0.4)

    if "bank" in lower:
        await session.emit("state", name="ACTING")
        await session.say("Switching to Bank Details tab.")
        await session.target_and_act("#tab-bank", "Bank Details Tab", "click")
        await session.emit("field_table", fields=[
            {"label": "Account Number", "value_masked": "••••••••1234", "status": "Filled"},
            {"label": "IFSC Code", "value_masked": "••••••••", "status": "Filled"},
        ])
        await session.emit("state", name="ANSWERING")
        await session.say("Bank details tab is open and fields are populated.")

    elif "personal" in lower:
        await session.emit("state", name="ACTING")
        await session.say("Switching to Personal Details tab.")
        await session.target_and_act("#tab-personal", "Personal Details Tab", "click")
        await session.emit("state", name="ANSWERING")
        await session.say("Switched to Personal Details tab.")

    elif "name" in lower or "fill" in lower:
        await session.emit("state", name="ACTING")
        await session.say("Entering full name into the application form.")
        await session.target_and_act("#full_name", "Full Name", "fill", "Ramesh Kumar")
        await session.emit("field_table", fields=[
            {"label": "Full Name", "value_masked": "Ramesh Kumar", "status": "Ready"},
            {"label": "PIN Code", "value_masked": "560001", "status": "Ready"},
        ])
        await session.emit("state", name="ANSWERING")
        await session.say("Full name entered successfully.")

    elif "submit" in lower or "apply" in lower:
        session.pending_confirmation = True
        await session.emit("state", name="AWAITING_CONFIRM")
        await session.emit("pending", description="Submit disability pension application to government portal.")
        await session.say("I am about to submit your pension application. Please say confirm to proceed, or stop to cancel.")

    else:
        # General assistance response
        await session.emit("state", name="ANSWERING")
        await session.say(f"I heard: {text}. Tell me what to click or fill on the portal.")

    await session.browser.refocus_console()


@app.websocket("/ws/console")
async def ws_console(ws: WebSocket) -> None:
    await ws.accept()
    log.info("Voice Console WebSocket connected")
    browser = getattr(app.state, "browser", None)
    session = M2HarnessSession(browser=browser, ws=ws)
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
        log.info("Voice Console WebSocket disconnected")


async def main() -> None:
    site_port = serve_mock_site(port=8000)
    backend_port = find_free_port([8080, 8081, 8090, 8888])

    # Start FastAPI server in background
    uvicorn_config = uvicorn.Config(app, host="127.0.0.1", port=backend_port, log_level="warning")
    server = uvicorn.Server(uvicorn_config)
    server_task = asyncio.create_task(server.serve())

    # Wait for backend health
    await asyncio.sleep(1)

    log.info("Launching side-by-side BrowserController (Console on :%s + Portal on :%s)...", backend_port, site_port)
    browser = BrowserController(console_url=f"http://127.0.0.1:{backend_port}/console")
    app.state.browser = browser
    await browser.start()

    # Navigate right window to the mock portal apply page
    await browser.goto(f"http://127.0.0.1:{site_port}/portal/apply.html")
    await browser.active.wait_for_load_state("domcontentloaded")

    # Inject visual feedback script into active page
    await browser.active.evaluate(TARGET_OVERLAY_SCRIPT)

    # Bring Console to foreground
    await browser.refocus_console()

    log.info("==================================================================")
    log.info("M2 Voice Console MVP is LIVE!")
    log.info("1. Left Window: Voice Console on http://127.0.0.1:%s/console", backend_port)
    log.info("2. Right Window: Disability Pension Portal on http://127.0.0.1:%s", site_port)
    log.info("3. Speak via Handy or type in Console (e.g., 'switch to bank details')")
    log.info("Press Ctrl+C to terminate.")
    log.info("==================================================================")

    try:
        await server_task
    except asyncio.CancelledError:
        pass
    finally:
        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("M2 Demo stopped by operator.")

