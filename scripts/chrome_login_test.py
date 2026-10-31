"""BRW-07 step 1 proof: does a Gmail sign-in survive a restart of Chrome started for the agent?

1. Starts the installed Chrome (not Playwright's) with remote debugging on 127.0.0.1 and the
   persistent agent profile (config.AGENT_PROFILE_DIR), opening Gmail.
2. You sign in to Gmail yourself in that window. This script never types anything.
3. Closes that Chrome, starts it again with the same profile, attaches over CDP, opens Gmail.
4. PASS if Gmail opens the inbox, FAIL if it sends you to a sign-in page.

Run from the repo root:  python scripts/chrome_login_test.py [--wait-minutes N]
In a terminal it waits for Enter after you sign in; otherwise it waits until the window reaches
the inbox (up to --wait-minutes). It prints only host names and yes/no checks, never page text.
"""
import argparse
import asyncio
import platform
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.async_api import async_playwright  # noqa: E402

from app import config  # noqa: E402
from app.browser import cdp_version as _cdp_version, chrome_command as _chrome_command  # noqa: E402
from app.browser import find_chrome, wait_for_cdp as _wait_for_cdp  # noqa: E402


def chrome_command(chrome: str, url: str) -> list[str]:
    return _chrome_command(chrome, config.CHROME_DEBUG_PORT, config.AGENT_PROFILE_DIR, url)


def cdp_version() -> dict | None:
    return _cdp_version(config.CDP_URL)


def wait_for_cdp() -> dict:
    return _wait_for_cdp(config.CDP_URL)

GMAIL = "https://mail.google.com/mail/u/0/#inbox"
INSECURE_WARNING = "may not be secure"   # Google's "This browser or app may not be secure"


def listening_addresses(port: int) -> list[str]:
    """Local addresses Chrome listens on for the debug port (to confirm it is 127.0.0.1 only)."""
    try:
        out = subprocess.run(["netstat", "-an"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    addrs = set()
    for line in out.splitlines():
        parts = line.split()
        if any(p.upper() == "LISTENING" or p.upper() == "LISTEN" for p in parts):
            for p in parts:
                if p.endswith(f":{port}") or p.endswith(f".{port}"):
                    addrs.add(p)
                    break
    return sorted(addrs)


def where(url: str) -> str:
    host = urlparse(url).hostname or ""
    if host == "mail.google.com" and urlparse(url).path.startswith("/mail"):
        return "inbox"
    if host.endswith("accounts.google.com") or "ServiceLogin" in url:
        return "sign-in"
    return host or "blank"


async def gmail_page(browser):
    """The tab showing the inbox if any, else a Google tab (signed-out Gmail opens on
    workspace.google.com and the user may sign in from another tab)."""
    pages = [p for c in browser.contexts for p in c.pages]
    return (next((p for p in pages if where(p.url) == "inbox"), None)
            or next((p for p in pages if "google.com" in p.url), pages[0] if pages else None))


async def stop_chrome(browser, proc: subprocess.Popen | None) -> None:
    """Close Chrome cleanly (so the profile saves its cookies), then make sure it is gone."""
    try:
        session = await browser.new_browser_cdp_session()
        await session.send("Browser.close")
    except Exception:
        pass
    if proc is None:   # a Chrome we reused: wait for its debug port to go quiet
        for _ in range(30):
            if cdp_version() is None:
                break
            await asyncio.sleep(0.5)
        await asyncio.sleep(2)   # let the profile finish writing
        return
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=10)


async def main(wait_minutes: float) -> int:
    chrome = find_chrome()
    if not chrome:
        print("FAIL: Chrome not found. Set CHROME_PATH in .env.")
        return 2
    already_running = cdp_version() is not None
    config.AGENT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"OS: {platform.system()} {platform.release()} ({platform.version()})")
    print(f"Chrome: {chrome}")
    print("Profile folder: AGENT_PROFILE_DIR (outside the repo)")

    async with async_playwright() as p:
        # Run 1: sign in by hand. Reuse the agent Chrome if an earlier run left it open.
        if already_running:
            print(f"Reusing the Chrome already answering on {config.CDP_URL}.")
            proc = None
        else:
            proc = subprocess.Popen(chrome_command(chrome, GMAIL))
        info = wait_for_cdp()
        print(f"Chrome version: {info.get('Browser')}")
        print(f"Remote debugging with this profile folder: worked ({config.CDP_URL})")
        print(f"Debug port listening on: {', '.join(listening_addresses(config.CHROME_DEBUG_PORT)) or 'unknown'}")
        browser = await p.chromium.connect_over_cdp(config.CDP_URL)
        print(f"Attached over CDP: {len(browser.contexts)} context(s)")

        page = await gmail_page(browser)
        if where(page.url) == "inbox":
            print("Already signed in from an earlier run.")
        else:
            print("Sign in to Gmail yourself in the Chrome window, press Enter here when you see your inbox.")
            try:
                if not sys.stdin.isatty():
                    raise EOFError
                await asyncio.get_running_loop().run_in_executor(None, input)
            except EOFError:   # no usable terminal (e.g. run from a tool): watch for the inbox instead
                print(f"(No terminal input: waiting up to {wait_minutes:g} minutes for the inbox to open.)")
                deadline = time.monotonic() + wait_minutes * 60
                while time.monotonic() < deadline:
                    page = await gmail_page(browser)
                    if page and where(page.url) == "inbox":
                        break
                    await asyncio.sleep(2)
        page = await gmail_page(browser)
        warned = False
        if page:
            try:
                warned = INSECURE_WARNING in (await page.content())
            except Exception:
                pass
        first = where(page.url) if page else "no page"
        print(f"Run 1 ends on: {first}; Google 'may not be secure' warning: {'yes' if warned else 'no'}")
        await stop_chrome(browser, proc)
        print("Chrome closed.")
        if first != "inbox":
            print("RESULT: FAIL (did not reach the inbox in run 1, so there was no sign-in to keep)")
            return 1

        # Run 2: same profile, fresh process.
        proc = subprocess.Popen(chrome_command(chrome, "about:blank"))
        wait_for_cdp()
        browser = await p.chromium.connect_over_cdp(config.CDP_URL)
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(GMAIL, wait_until="domcontentloaded")
        for _ in range(30):               # Gmail redirects a few times before settling
            if where(page.url) in ("inbox", "sign-in"):
                break
            await asyncio.sleep(1)
        second = where(page.url)
        print(f"Run 2 (restarted Chrome, same profile) lands on: {second}")
        await stop_chrome(browser, proc)
        print("Chrome closed.")
        result = "PASS" if second == "inbox" else "FAIL"
        print(f"RESULT: {result}")
        return 0 if result == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wait-minutes", type=float, default=5)
    sys.exit(asyncio.run(main(parser.parse_args().wait_minutes)))
