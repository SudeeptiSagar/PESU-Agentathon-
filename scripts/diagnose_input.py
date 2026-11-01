"""ONE command that finds out why the Console / Handy input fails on a laptop. Owner: M1.

    python scripts/diagnose_input.py             # about 90 seconds; browser windows flash on screen, hands off
    python scripts/diagnose_input.py --handy 3   # then 3 real rounds where YOU speak through your Handy key

It prints one block of plain text, also saved to a file whose path is shown at the end. Copy everything from the
line "START" to the last line and send it. It contains no passwords, no profile data and no page content: only
versions, file sizes, which of four .env settings are set, graphics driver names, and yes/no results.
"""
import argparse
import asyncio
import contextlib
import io
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

STATE_JS = """() => {
  const c = document.createElement('canvas');
  const gl = c.getContext('webgl2') || c.getContext('webgl');
  let renderer = 'no WebGL';
  if (gl) { const i = gl.getExtension('WEBGL_debug_renderer_info');
            renderer = i ? String(gl.getParameter(i.UNMASKED_RENDERER_WEBGL)) : 'hidden by the browser'; }
  const input = document.querySelector('.capture-input');
  return {root: document.getElementById('root') ? document.getElementById('root').children.length : -1,
          input: !!input, focused: !!input && document.activeElement === input,
          plain: !!document.querySelector('.plain-orb'), canvas: !!document.querySelector('canvas'),
          renderer: renderer.slice(0, 70), title: document.title.slice(0, 40)};
}"""
summary: list[str] = []


def short(text, n=100) -> str:
    return " ".join(str(text).split())[:n]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        return "unknown"


async def section(title: str, work) -> None:
    print(f"\n{title}")
    try:
        await work()
    except Exception as e:  # one broken section must not hide the others
        print(f"  ERROR in this section: {type(e).__name__}: {short(e)}")
        summary.append(f"{title.split('.')[0]}. {type(e).__name__}")


async def versions() -> None:
    from app import config
    page = ROOT / "client" / "console.html"
    fixed = page.is_file() and "plain-orb" in page.read_text(encoding="utf-8", errors="ignore")
    print(f"  git: {git('rev-parse', '--abbrev-ref', 'HEAD')} @ {git('rev-parse', '--short', 'HEAD')} "
          f"({short(git('log', '-1', '--format=%s'), 60)})")
    print(f"  {platform.platform()} | Python {platform.python_version()}")
    print(f"  .env: BROWSER_MODE={config.BROWSER_MODE} BROWSER_HEADLESS={config.BROWSER_HEADLESS} "
          f"TTS_BACKEND={config.TTS_BACKEND} STT_BACKEND={config.STT_BACKEND}")
    print(f"  client/console.html: {page.stat().st_size // 1024 if page.is_file() else 'MISSING'} KB, "
          f"orb-fallback fix inside: {'yes' if fixed else 'NO (old Console)'}")
    summary.append(f"orb fix in the Console: {'yes' if fixed else 'NO, old Console'}")


async def serving(port: int) -> None:
    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/console", timeout=5).read().decode("utf-8", "ignore")
    health = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5).read().decode()
    kind = ("PLACEHOLDER page (no orb at all!)" if "Voice Console (placeholder)" in body
            else "the real Console" if "PESU Agent Voice Console" in body else "something unexpected")
    print(f"  /console serves: {kind}, {len(body) // 1024} KB")
    print(f"  /health: {short(health, 150)}")
    summary.append(f"/console serves: {kind}")


async def console_in(mode: str, port: int) -> None:
    from app.browser import BrowserController
    browser = BrowserController(console_url=f"http://127.0.0.1:{port}/console", mode=mode)
    try:
        await browser.start()
    except Exception as e:
        print(f"  [{mode}] could not start this browser: {type(e).__name__}: {short(e)}")
        summary.append(f"{mode}: could not start")
        return
    try:
        page = browser.console_page
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(short(e, 90)))
        await page.reload()
        await page.wait_for_timeout(3000)
        state = await page.evaluate(STATE_JS)
        typed = False
        if state["input"]:
            await page.keyboard.type("hello")
            typed = await page.evaluate("document.querySelector('.capture-input').value") == "hello"
        orb = "real WebGL orb" if state["canvas"] else "plain circle" if state["plain"] else "NOTHING (page is blank)"
        print(f"  [{mode}] graphics: {state['renderer']}")
        print(f"  [{mode}] page: {orb} | input box: {state['input']} | has keyboard focus: {state['focused']} | typing works: {typed}")
        print(f"  [{mode}] page errors: {errors[:2] or 'none'}")
        ok = state["input"] and typed
        summary.append(f"{mode}: input {'WORKS' if ok else 'BROKEN'}, shows {orb}")
        if not ok:                                                     # separate the orb from the input
            await page.goto(f"http://127.0.0.1:{port}/console?orb=off")
            await page.wait_for_timeout(2000)
            again = await page.evaluate(STATE_JS)
            if again["input"]:
                await page.keyboard.type("hello")
                again["typed"] = await page.evaluate("document.querySelector('.capture-input').value") == "hello"
            print(f"  [{mode}] retried with ?orb=off -> input box: {again['input']}, typing works: {again.get('typed', False)}")
            summary.append(f"{mode} with ?orb=off: input {'WORKS' if again.get('typed') else 'STILL BROKEN'}")
    finally:
        await browser.close()


async def focus(handy_rounds: int) -> None:
    import focus_diag
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = await focus_diag.main(0)
    text = buffer.getvalue()
    for line in text.splitlines():
        # the bullet list of working strategies and the "send this to Prashanth" line only repeat the table above
        if line.strip() and not line.startswith("   - ") and not line.startswith("Send this whole output"):
            print("  " + line[:96])
    summary.append("window focus: " + ("a strategy works every time" if code == 0 else "NO strategy worked every time"))
    if handy_rounds:
        print("\n  (now the Handy rounds: speak when asked)")
        await focus_diag.main(handy_rounds)


async def main(handy_rounds: int) -> int:
    for stream in (sys.__stdout__, sys.__stderr__):          # a Windows terminal must never crash on a character
        with contextlib.suppress(Exception):
            stream.reconfigure(errors="replace")
    lines = io.StringIO()

    class Tee:
        def write(self, text):
            sys.__stdout__.write(text)
            lines.write(text)

        def flush(self):
            sys.__stdout__.flush()

    tee = Tee()
    port = free_port()
    env = dict(os.environ, PORT=str(port), HOST="127.0.0.1", BROWSER_HEADLESS="false", AUTO_UNLOCK="false",
               PROFILE_PATH=str(Path(tempfile.gettempdir()) / "diagnose_input_no_profile" / "profile.json"))
    server = subprocess.Popen([sys.executable, "-m", "app.main"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with contextlib.redirect_stdout(tee):
        print("=" * 22 + " START (copy from here to the last line) " + "=" * 22)
        try:
            await section("1. VERSIONS", versions)
            for _ in range(80):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
                    break
                except Exception:
                    time.sleep(0.25)
            await section("2. WHAT THE BACKEND SHOWS AT /console", lambda: serving(port))
            await section("3. THE REAL CONSOLE IN THIS LAPTOP'S BROWSERS", lambda: both_browsers(port))
            await section("4. WINDOW FOCUS (how Handy's paste finds the Console)", lambda: focus(handy_rounds))
        finally:
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
        print("\n5. SUMMARY")
        for item in summary:
            print("  - " + item)
        print("=" * 30 + " END " + "=" * 30)
    out = Path(tempfile.gettempdir()) / "diagnose_input_output.txt"
    out.write_text(lines.getvalue(), encoding="utf-8")
    print(f"\n(also saved to {out})")
    return 0


async def both_browsers(port: int) -> None:
    for mode in ("chromium", "chrome"):
        await console_in(mode, port)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--handy", type=int, default=0, metavar="N", help="then N real rounds through your Handy hotkey")
    sys.exit(asyncio.run(main(ap.parse_args().handy)))
