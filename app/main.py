"""FastAPI backend: health, Voice Console page and the Console WebSocket (PRD Sections 7, 12).

Owner: M1. Run with `python -m app.main` (http://localhost:8080, Console at /console).
"""
import logging

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse

from app import agent, config
from app.session import Context, Session
from app.voice import PiperTTS

log = logging.getLogger("app.main")
app = FastAPI(title="Voice Browser Agent")

CONSOLE_HTML = config.ROOT / "client" / "console.html"

_PLACEHOLDER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Voice Console (placeholder)</title>
<style>body{font:1.5rem system-ui;background:#000;color:#fff;margin:2rem}
input{font:inherit;width:100%;padding:.5rem}#log{white-space:pre-wrap}</style></head>
<body><h1>Voice Console (placeholder)</h1>
<p>client/console.html is not built yet (UI-02). Type and press Enter to test the WebSocket.</p>
<input id="box" autofocus aria-label="Say or type a request">
<div id="log" role="log" aria-live="polite"></div>
<script>
const ws = new WebSocket(`ws://${location.host}/ws/console`), log = document.getElementById("log"),
      box = document.getElementById("box");
ws.onmessage = e => { log.textContent += e.data + "\n"; };
box.onkeydown = e => {
  if (e.key === "Enter" && box.value.trim()) {
    ws.send(JSON.stringify({type: "utterance", text: box.value})); box.value = "";
  } else if (e.key === "Escape") ws.send(JSON.stringify({type: "key", name: "Escape"}));
};
</script></body></html>"""


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": config.LLM_MODEL, "tts": config.TTS_BACKEND,
            "stt": config.STT_BACKEND, "gate": config.GATE_BACKEND}


@app.get("/console", response_model=None)
async def console() -> FileResponse | HTMLResponse:
    if CONSOLE_HTML.exists():
        return FileResponse(CONSOLE_HTML)
    return HTMLResponse(_PLACEHOLDER)


@app.websocket("/ws/console")
async def ws_console(ws: WebSocket) -> None:
    await ws.accept()
    ctx = Context(session=Session(), send=ws.send_json,
                  tts=PiperTTS() if config.TTS_BACKEND == "piper" else None)
    await ctx.emit("state", name=ctx.session.state)
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "utterance" and str(msg.get("text", "")).strip():
                await agent.handle_utterance(msg["text"].strip(), ctx)
            elif kind == "key" and msg.get("name") == "Escape":
                await agent.stop(ctx)
            else:
                await ctx.emit("alert", level="warning", message=f"Unknown event: {kind}")
    except WebSocketDisconnect:
        log.info("console disconnected")


def main() -> None:
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
