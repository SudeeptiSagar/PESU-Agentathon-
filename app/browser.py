"""Playwright browser controller: agent window, Console window, tabs (PRD Section 12).

Owner: M3 (Sudeepti). One headed Chromium process with two windows: the agent browses in one
context (its tabs are what list_tabs/switch_tab see), the Voice Console lives in another so that
Handy's paste always has a text box to land in (PRD 8.3).
"""
import asyncio
import inspect
import logging
import sys
from typing import Any, Callable

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app import config

log = logging.getLogger(__name__)

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


class BrowserController:
    def __init__(self, on_new_tab: Callable[[str, str], Any] | None = None,
                 headless: bool = False, console_url: str = CONSOLE_URL) -> None:
        self.on_new_tab = on_new_tab   # called as on_new_tab(title, url); may be sync or async
        self.headless = headless
        self.console_url = console_url
        self.active: Page | None = None        # current agent page (tab)
        self.console_page: Page | None = None  # Voice Console page
        self._pages: list[Page] = []           # agent tabs, in opening order
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._agent_ctx: BrowserContext | None = None
        self._console_ctx: BrowserContext | None = None
        self._tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Launch headed Chromium with the agent window and the Console window."""
        self._pw = await async_playwright().start()
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
        await self.refocus_console()

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
            await self._agent_ctx.new_page()

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
        for task in list(self._tasks):
            task.cancel()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._browser = self._pw = None
        self.active = self.console_page = None
        self._pages = []

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
