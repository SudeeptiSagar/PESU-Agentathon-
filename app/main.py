"""FastAPI backend: health, Voice Console page and the Console WebSocket (PRD Sections 7, 12).

Owner: M1. Run with `python -m app.main` (http://localhost:8080, Console at /console).

One user, one Session: every Console connection shares the same Context, so refreshing the Console
page never starts a second browser or loses the task. The browser is started on demand ("open chrome"
or the first task), see agent.ensure_browser.

The Console is the built React app in client/dist (cd client; npm ci; npm run build). Until it is
built, /console shows a small placeholder page that works with the same WebSocket.
"""
import asyncio
import contextlib
import json
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse

from app import agent, config, tools
from app.browser import BrowserController
from app.session import Context, Session
from app.voice import PiperTTS

log = logging.getLogger("app.main")

CLIENT_DIR = config.ROOT / "client"
DIST_DIR = CLIENT_DIR / "dist"
MAX_UTTERANCE_CHARS = 2000
DEV_PORT = 5173          # the Vite dev server for the Console
# Browsers may not guess these on every OS (Windows can map .js to text/plain, which module scripts refuse).
MEDIA_TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".map": "application/json",
               ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".json": "application/json"}

_PLACEHOLDER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Voice Console (placeholder)</title>
<style>body{font:1.5rem system-ui;background:#000;color:#fff;margin:2rem}
input{font:inherit;width:100%;padding:.5rem}#log{white-space:pre-wrap}</style></head>
<body><h1>Voice Console (placeholder)</h1>
<p>The Console is not built yet. In the client folder run <code>npm ci</code> and <code>npm run build</code>,
then reload. Meanwhile you can type here and press Enter.</p>
<input id="box" autofocus aria-label="Say or type a request">
<div id="log" role="log" aria-live="polite"></div>
<script>
const ws = new WebSocket(`ws://${location.host}/ws/console`), log = document.getElementById("log"),
      box = document.getElementById("box");
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.type === "speak") log.textContent += m.text + "\\n"; };
box.onkeydown = e => {
  if (e.key === "Enter" && box.value.trim()) {
    ws.send(JSON.stringify({type: "utterance", text: box.value})); box.value = "";
  } else if (e.key === "Escape") ws.send(JSON.stringify({type: "key", name: "Escape"}));
  else if (e.code === "Space" && !box.value) { e.preventDefault(); ws.send(JSON.stringify({type: "key", name: "Space"})); }
};
</script></body></html>"""


class Hub:
    """The one shared Context and the Console sockets that currently listen to it."""

    def __init__(self, browser_factory) -> None:
        self.sockets: set[WebSocket] = set()
        self.ctx = Context(session=Session(), send=self.broadcast,
                           tts=PiperTTS() if config.TTS_BACKEND == "piper" else None,
                           browser_factory=(lambda: browser_factory(self)) if browser_factory else None)

    async def broadcast(self, event: dict) -> None:
        for ws in list(self.sockets):
            try:
                await ws.send_json(event)
            except Exception:       # that Console went away
                self.sockets.discard(ws)

    async def shutdown(self) -> None:
        task, self.ctx.task = self.ctx.task, None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self.ctx.browser is not None:
            with contextlib.suppress(Exception):
                await self.ctx.browser.close()


def make_browser(hub: Hub) -> BrowserController:
    """The real browser. New tabs are announced aloud (never with saved values in the title)."""
    async def on_new_tab(title: str, url: str) -> None:
        await hub.ctx.say("A new tab opened: " + tools.hide_profile_text(title or url, hub.ctx.session.profile))
    return BrowserController(on_new_tab=on_new_tab, headless=config.BROWSER_HEADLESS)


_UNSET = object()


def get_hub() -> Hub:
    hub = getattr(app.state, "hub", None)
    if hub is None:
        factory = getattr(app.state, "browser_factory", _UNSET)   # tests set this (None = no browser)
        hub = app.state.hub = Hub(make_browser if factory is _UNSET else factory)
    return hub


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    hub = getattr(app.state, "hub", None)
    if hub is not None:
        await hub.shutdown()


app = FastAPI(title="Voice Browser Agent", lifespan=lifespan)


# ---------------------------------------------------------------- pages
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": config.LLM_MODEL, "tts": config.TTS_BACKEND, "stt": config.STT_BACKEND,
            "gate": config.GATE_BACKEND, "browser": config.BROWSER_MODE,
            "console_built": (DIST_DIR / "console.html").is_file()}


@app.get("/console", response_model=None)
async def console() -> FileResponse | HTMLResponse:
    built = DIST_DIR / "console.html"
    if built.is_file():
        return FileResponse(built, media_type="text/html")
    return HTMLResponse(_PLACEHOLDER)


@app.get("/assets/{path:path}", response_model=None)
async def console_assets(path: str) -> FileResponse:
    base = (DIST_DIR / "assets").resolve()
    target = (base / path).resolve()
    if base not in target.parents or not target.is_file():       # also stops ../ escapes
        raise HTTPException(status_code=404)
    return FileResponse(target, media_type=MEDIA_TYPES.get(target.suffix.lower()))


# ---------------------------------------------------------------- the Console socket
def allowed_origins() -> set[str]:
    hosts = {config.HOST, "localhost", "127.0.0.1"}
    return {f"http://{h}:{p}" for h in hosts for p in (config.PORT, DEV_PORT)}


def origin_ok(ws: WebSocket) -> bool:
    """A browser always sends Origin. Only our own Console page may talk to the agent: otherwise any web
    page in the agent's browser could connect and send "confirm". Non-browser clients send none."""
    origin = ws.headers.get("origin")
    return origin is None or origin.rstrip("/") in allowed_origins()


async def alert(hub: Hub, level: str, message: str) -> None:
    await hub.ctx.emit("alert", level=level, message=message)


async def handle_message(hub: Hub, msg) -> None:
    if not isinstance(msg, dict):
        return await alert(hub, "warning", "Unknown message.")
    kind = msg.get("type")
    if kind == "utterance":
        text = msg.get("text")
        text = text.strip() if isinstance(text, str) else ""
        if not text:
            return
        if len(text) > MAX_UTTERANCE_CHARS:
            return await alert(hub, "warning", "That was too long for me to handle. Please say it in parts.")
        return await agent.handle_utterance(text, hub.ctx)
    if kind == "key" and msg.get("name") == "Escape":
        return await agent.stop(hub.ctx)
    if kind == "key" and msg.get("name") == "Space":
        return await agent.toggle_pause(hub.ctx)
    await alert(hub, "warning", f"Unknown event: {str(kind)[:30]}")


@app.websocket("/ws/console")
async def ws_console(ws: WebSocket) -> None:
    if not origin_ok(ws):
        log.warning("refused a Console connection from origin %s", ws.headers.get("origin"))
        await ws.close(code=1008)
        return
    await ws.accept()
    hub = get_hub()
    hub.sockets.add(ws)
    try:
        await ws.send_json({"type": "state", "name": hub.ctx.session.state})
        while True:
            try:
                msg = await ws.receive_json()
            except json.JSONDecodeError:
                await alert(hub, "warning", "I could not read that message.")
                continue
            try:
                await handle_message(hub, msg)
            except Exception as e:      # one bad message must not end the Console connection
                log.exception("error handling a Console message: %s", type(e).__name__)
                await alert(hub, "error", "Something went wrong. Please try again.")
    except WebSocketDisconnect:
        log.info("console disconnected")
    finally:
        hub.sockets.discard(ws)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    built = (DIST_DIR / "console.html").is_file()
    log.info("Console: http://%s:%s/console (%s)", config.HOST, config.PORT,
             "built" if built else "not built, showing the placeholder: cd client; npm ci; npm run build")
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
