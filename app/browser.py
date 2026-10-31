"""Playwright browser controller: agent window, Console window, tabs (PRD Section 12).

Owner: M3 (Sudeepti). Two windows: the agent browses in one (its tabs are what list_tabs and
switch_tab see), the Voice Console lives in the other so that Handy's paste always has a text
box to land in (PRD 8.3).

Modes (config.BROWSER_MODE, PRD 3.2):
  chromium  Playwright's bundled Chromium, fresh each time; two contexts = two windows (default).
  chrome    the installed Chrome with remote debugging on 127.0.0.1 and the persistent agent
            profile (AGENT_PROFILE_DIR), started here if nothing answers on CDP_URL, then
            attached over CDP. The user signs in to sites once by hand; later sessions stay
            signed in.
  attach    attach over CDP to a Chrome that is already running; error if none is.
In chrome and attach modes both windows live in the profile's default context
(browser.contexts[0], the signed-in one), and only tabs in the agent's window are agent tabs.
"""
import asyncio
import inspect
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app import config

log = logging.getLogger(__name__)

MODES = ("chromium", "chrome", "attach")
CONSOLE_URL = f"http://{config.HOST}:{config.PORT}/console"
CONSOLE_BOUNDS = {"left": 0, "top": 0, "width": 520, "height": 900}
AGENT_BOUNDS = {"left": 530, "top": 0, "width": 1100, "height": 900}
# Focus the Console's text box. The Console (M2) keeps focus itself; this is a backstop.
FOCUS_INPUT_JS = """() => {
  window.focus();
  const box = document.querySelector('textarea, input[type=text], input:not([type])');
  if (box) box.focus();
  return document.hasFocus();
}"""


def _win_force_foreground(title_part: str) -> bool:
    """Windows only: make the top-level window whose title contains title_part the OS foreground.

    Windows refuses SetForegroundWindow from a background process; attaching our input queue to
    the current foreground thread lifts that restriction for the call (PRD 8.3 OS-level helper).
    """
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            if title_part and title_part in buf.value:
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(visit, 0)
    if not found:
        return False
    hwnd = found[0]
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    our_thread = kernel32.GetCurrentThreadId()
    attached = fg_thread != our_thread and user32.AttachThreadInput(our_thread, fg_thread, True)
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(our_thread, fg_thread, False)
    return user32.GetForegroundWindow() == hwnd


class BrowserStartError(RuntimeError):
    """The browser could not be started or attached (message is safe to speak to the user)."""


def find_chrome(chrome_path: str | None = None, platform: str | None = None,
                env: dict | None = None) -> str | None:
    """Path to the installed Chrome: chrome_path (CHROME_PATH) if set, else the usual install
    locations for the OS. None if not found."""
    chrome_path = config.CHROME_PATH if chrome_path is None else chrome_path
    platform = platform or sys.platform
    env = os.environ if env is None else env
    if chrome_path:
        return chrome_path if Path(chrome_path).is_file() else None
    if platform == "win32":
        bases = [env.get(v) for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        candidates = [Path(b) / "Google" / "Chrome" / "Application" / "chrome.exe" for b in bases if b]
    elif platform == "darwin":
        app = "Google Chrome.app/Contents/MacOS/Google Chrome"
        candidates = [Path("/Applications") / app, Path(env.get("HOME", str(Path.home()))) / "Applications" / app]
    else:
        found = [shutil.which(n) for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")]
        candidates = [Path(f) for f in found if f]
    return next((str(c) for c in candidates if c.is_file()), None)


def chrome_command(chrome: str, port: int, profile_dir: Path | str, url: str = "about:blank") -> list[str]:
    """Command line for the agent's Chrome. Remote debugging listens on loopback because no
    --remote-debugging-address is given. Chrome 136+ ignores the debug port on the default
    profile, so a separate --user-data-dir is required. Nothing hides the automation."""
    return [chrome, f"--remote-debugging-port={port}", f"--user-data-dir={profile_dir}",
            "--no-first-run", "--no-default-browser-check", url]


def cdp_version(cdp_url: str) -> dict | None:
    """Chrome's /json/version answer, or None if nothing is listening."""
    try:
        with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=1) as r:
            return json.load(r)
    except Exception:
        return None


def wait_for_cdp(cdp_url: str, seconds: float = 20) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        info = cdp_version(cdp_url)
        if info:
            return info
        time.sleep(0.3)
    raise BrowserStartError(f"Chrome did not answer on {cdp_url} within {seconds:.0f} seconds")


class BrowserController:
    def __init__(self, on_new_tab: Callable[[str, str], Any] | None = None,
                 headless: bool = False, console_url: str = CONSOLE_URL, mode: str | None = None,
                 debug_port: int | None = None, profile_dir: Path | str | None = None,
                 chrome_path: str | None = None) -> None:
        self.on_new_tab = on_new_tab   # called as on_new_tab(title, url); may be sync or async
        self.headless = headless       # chromium mode only
        self.console_url = console_url
        self.mode = mode or config.BROWSER_MODE
        if self.mode not in MODES:
            raise ValueError(f"BROWSER_MODE must be one of {', '.join(MODES)}, got {self.mode!r}")
        self.debug_port = debug_port or config.CHROME_DEBUG_PORT
        self.cdp_url = f"http://127.0.0.1:{self.debug_port}"   # local only (PRD 3.2)
        self.profile_dir = Path(profile_dir or config.AGENT_PROFILE_DIR)
        self.chrome_path = chrome_path
        self._proc: subprocess.Popen | None = None   # the Chrome we started, if any
        self._agent_window: int | None = None
        self.active: Page | None = None        # current agent page (tab)
        self.console_page: Page | None = None  # Voice Console page
        self._pages: list[Page] = []           # agent tabs, in opening order
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._agent_ctx: BrowserContext | None = None
        self._console_ctx: BrowserContext | None = None
        self._tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Open the agent window and the Console window, in the browser config.BROWSER_MODE picks."""
        self._pw = await async_playwright().start()
        try:
            if self.mode == "chromium":
                await self._start_chromium()
            else:
                await self._start_cdp()
        except BaseException:
            await self.close()
            raise
        await self.refocus_console()

    async def _start_chromium(self) -> None:
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        # Separate contexts open as separate windows; no_viewport lets each page fill its window.
        self._console_ctx = await self._browser.new_context(no_viewport=True)
        self._agent_ctx = await self._browser.new_context(no_viewport=True)

        self.console_page = await self._console_ctx.new_page()
        await self._place_window(self._console_ctx, self.console_page, CONSOLE_BOUNDS)
        try:
            await self.console_page.goto(self.console_url)
        except Exception as e:  # backend not up yet: keep the window, the agent can still browse
            log.warning("Console not reachable at %s: %s", self.console_url, e)

        self._agent_ctx.on("page", self._on_page)
        self.active = await self._agent_ctx.new_page()   # _on_page registers it
        await self._place_window(self._agent_ctx, self.active, AGENT_BOUNDS)

    async def _start_cdp(self) -> None:
        """chrome / attach: attach to Chrome over CDP, starting it first in chrome mode."""
        if await asyncio.to_thread(cdp_version, self.cdp_url) is None:
            if self.mode == "attach":
                raise BrowserStartError(
                    f"No Chrome is listening on {self.cdp_url}. Start Chrome with "
                    f"--remote-debugging-port={self.debug_port} --user-data-dir=<a separate profile folder>, "
                    "or set BROWSER_MODE=chrome to let the agent start it.")
            chrome = find_chrome(self.chrome_path)
            if not chrome:
                raise BrowserStartError("Google Chrome was not found. Install it or set CHROME_PATH in .env.")
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            self._proc = subprocess.Popen(chrome_command(chrome, self.debug_port, self.profile_dir))
            await asyncio.to_thread(wait_for_cdp, self.cdp_url)
        self._browser = await self._pw.chromium.connect_over_cdp(self.cdp_url)
        ctx = self._browser.contexts[0]   # the profile's default, signed-in context
        self._agent_ctx = self._console_ctx = ctx
        startup_pages = list(ctx.pages)

        self.console_page = await self._new_window()
        await self._place_window(ctx, self.console_page, CONSOLE_BOUNDS)
        try:
            await self.console_page.goto(self.console_url)
        except Exception as e:  # backend not up yet: keep the window, the agent can still browse
            log.warning("Console not reachable at %s: %s", self.console_url, e)

        await self._open_agent_window()
        ctx.on("page", self._on_cdp_page)
        if self._proc:   # the blank startup window of a Chrome we started is not needed
            for page in startup_pages:
                await page.close()

    async def _open_agent_window(self) -> None:
        page = await self._new_window()
        self._agent_window = await self._window_id(page)
        await self._place_window(self._agent_ctx, page, AGENT_BOUNDS)
        self._on_page(page)

    async def _new_window(self) -> Page:
        """A new top-level window in the default context (CDP Target.createTarget, newWindow)."""
        session = await self._browser.new_browser_cdp_session()
        try:
            async with self._agent_ctx.expect_page() as info:
                await session.send("Target.createTarget", {"url": "about:blank", "newWindow": True})
            return await info.value
        finally:
            await session.detach()

    async def _window_id(self, page: Page) -> int | None:
        try:
            session = await self._agent_ctx.new_cdp_session(page)
            window = await session.send("Browser.getWindowForTarget")
            await session.detach()
            return window["windowId"]
        except Exception:
            return None

    def _on_cdp_page(self, page: Page) -> None:
        """chrome / attach: a tab opened in the agent's window is an agent tab; tabs the user opens
        in other windows of their Chrome are left alone."""
        task = asyncio.create_task(self._adopt_if_agent_tab(page))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _adopt_if_agent_tab(self, page: Page) -> None:
        if page is self.console_page or page in self._pages:
            return
        if self._agent_window is not None and await self._window_id(page) == self._agent_window:
            self._on_page(page)

    async def goto(self, url: str) -> None:
        await self.active.goto(url)

    async def list_tabs(self) -> list[dict]:
        return [{"index": i, "title": await p.title(), "url": p.url, "active": p is self.active}
                for i, p in enumerate(self._pages)]

    async def switch_tab(self, index: int) -> None:
        page = self._page_at(index)
        await page.bring_to_front()
        self.active = page

    async def close_tab(self, index: int) -> None:
        await self._page_at(index).close()   # _on_close updates the list and active tab
        if not self._pages:                  # never leave the agent without a tab
            if self.mode == "chromium":
                await self._agent_ctx.new_page()
            else:                            # its window closed with its last tab
                await self._open_agent_window()

    async def go_back(self) -> None:
        await self.active.go_back()

    async def refocus_console(self) -> None:
        """Bring the Console window to the front and focus its text box (PRD 8.3)."""
        if self.console_page is None or self.console_page.is_closed():
            return
        await self.console_page.bring_to_front()
        if sys.platform == "win32" and not self.headless:
            # bring_to_front cannot take OS focus from another app (Windows foreground lock)
            try:
                title = await self.console_page.title()
                for _ in range(3):
                    if _win_force_foreground(title):
                        break
                    await asyncio.sleep(0.1)
                else:
                    log.warning("Could not give the Console OS focus")
            except Exception as e:
                log.debug("OS refocus failed: %s", e)
        try:
            await self.console_page.evaluate(FOCUS_INPUT_JS)
        except Exception as e:  # page still loading or navigated away
            log.debug("Console focus script failed: %s", e)

    async def close(self) -> None:
        """chromium: close the browser. chrome / attach: a Chrome we started is shut down (its
        profile folder stays); one we did not start keeps running, only our windows close."""
        for task in list(self._tasks):
            task.cancel()
        if self._browser and self.mode != "chromium":
            if self._proc:
                try:
                    session = await self._browser.new_browser_cdp_session()
                    await session.send("Browser.close")   # clean exit, so the profile saves its cookies
                except Exception:
                    pass
            else:
                for page in [self.console_page, *self._pages]:
                    if page and not page.is_closed():
                        try:
                            await page.close()
                        except Exception:
                            pass
        if self._browser:
            await self._browser.close()   # chromium: closes it; over CDP: only disconnects
        if self._proc:
            try:
                await asyncio.to_thread(self._proc.wait, 15)
            except subprocess.TimeoutExpired:
                self._proc.terminate()
                await asyncio.to_thread(self._proc.wait, 10)
            self._proc = None
        if self._pw:
            await self._pw.stop()
        self._browser = self._pw = None
        self.active = self.console_page = None
        self._pages = []
        self._agent_window = None

    # Internals

    def _page_at(self, index: int) -> Page:
        if not 0 <= index < len(self._pages):
            raise IndexError(f"No tab {index}; there are {len(self._pages)} tabs")
        return self._pages[index]

    def _on_page(self, page: Page) -> None:
        """Every new agent tab (ours or a popup/target=_blank) becomes the active tab."""
        opened_by_page = bool(self._pages)
        self._pages.append(page)
        self.active = page
        page.on("close", self._on_close)
        if opened_by_page:
            task = asyncio.create_task(self._announce(page))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    def _on_close(self, page: Page) -> None:
        if page in self._pages:
            self._pages.remove(page)
        if self.active is page:
            self.active = self._pages[-1] if self._pages else None

    async def _announce(self, page: Page) -> None:
        try:
            await page.wait_for_load_state("domcontentloaded")
            title = await page.title()
        except Exception:
            title = ""
        if self.on_new_tab:
            result = self.on_new_tab(title or page.url, page.url)
            if inspect.isawaitable(result):
                await result

    async def _place_window(self, ctx: BrowserContext, page: Page, bounds: dict) -> None:
        """Position a window side by side with the other (best effort; needs a headed browser)."""
        if self.headless:
            return
        try:
            cdp = await ctx.new_cdp_session(page)
            window = await cdp.send("Browser.getWindowForTarget")
            await cdp.send("Browser.setWindowBounds",
                           {"windowId": window["windowId"], "bounds": bounds})
            await cdp.detach()
        except Exception as e:
            log.debug("Window placement failed: %s", e)
