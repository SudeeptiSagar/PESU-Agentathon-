"""Try the agent loop with typed requests: no microphone, no Console page (CORE-10 check). Owner: M1.

    python scripts/run_task.py "find out where Kalpana Chawla was born"
    python scripts/run_task.py --mock "apply for the disability pension on the demo portal"

It opens the real browser, uses the real model (Ollama) and prints what the agent says and does.
When the agent asks something or holds an irreversible action, type your answer at the prompt:
yes, no, confirm, done, stop, or any sentence. Type quit to leave.

--mock   serve mock_site on http://localhost:8000 and point web_search at the mock search page,
         so no real website is touched (the "demo portal", "demo shop" and "demo mail" aliases need it).
--demo-profile   use the fictional DEMO_PROFILE in memory (no PIN, nothing written to disk). Without it
         the agent runs with an empty profile, so it cannot fill forms.
"""
import argparse
import asyncio
import copy
import functools
import http.server
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import agent, config  # noqa: E402
from app.browser import BrowserController  # noqa: E402
from app.profile import DEMO_PROFILE  # noqa: E402
from app.session import Context, Session  # noqa: E402

MOCK_SITE = Path(__file__).resolve().parent.parent / "mock_site"


def serve_mock_site(port: int = 8000) -> http.server.ThreadingHTTPServer:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Quiet, directory=str(MOCK_SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def describe(event: dict) -> str | None:
    kind = event["type"]
    if kind == "speak":
        return f"AGENT: {event['text']}"
    if kind == "step":
        return f"  step {event['n']}: {event['action']}({event['target']}) -> {event['result']}"
    if kind == "pending":
        return f"HELD:  {event['description']}"
    if kind == "alert":
        return f"  [{event['level']}] {event['message']}"
    if kind == "state":
        return f"  (state: {event['name']})"
    return None


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("request", nargs="?", help="what to ask first; otherwise you are prompted")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--demo-profile", action="store_true")
    args = ap.parse_args()

    if args.mock:
        serve_mock_site()
        config.SEARCH_URL = "http://localhost:8000/web/search.html?q={q}"
    print(f"Model {config.LLM_MODEL}, browser mode {config.BROWSER_MODE}, search {config.SEARCH_URL}")

    async def send(event: dict) -> None:
        line = describe(event)
        if line:
            print(line, flush=True)

    session = Session(profile=copy.deepcopy(DEMO_PROFILE) if args.demo_profile else {})
    ctx = Context(session=session, send=send, browser_factory=BrowserController)
    text = args.request
    try:
        while True:
            if text is None:
                text = await asyncio.to_thread(input, "you> ")
            if text.strip().lower() in ("quit", "exit"):
                break
            await agent.handle_utterance(text, ctx)
            if ctx.task is not None:
                try:
                    await ctx.task
                except asyncio.CancelledError:
                    pass
            text = None
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        if ctx.task is not None and not ctx.task.done():
            ctx.task.cancel()
        if ctx.browser is not None:
            await ctx.browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
