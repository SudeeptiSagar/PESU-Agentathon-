"""Playwright browser controller: agent window, Console window, tabs (PRD Section 12).

Owner: M3 (Sudeepti). CORE-01 contract stubs; replace the bodies, keep the signatures.
"""
from typing import Any, Callable


class BrowserController:
    def __init__(self, on_new_tab: Callable[[str, str], Any] | None = None) -> None:
        self.on_new_tab = on_new_tab   # called as on_new_tab(title, url)
        self.active = None             # current agent page (tab)
        self.console_page = None       # Voice Console page
        self._tabs = [{"index": 0, "title": "New Tab", "url": "about:blank", "active": True}]

    async def start(self) -> None:
        """Launch headed Chromium with the agent window and the Console window."""
        # STUB: BRW-02
        return None

    async def goto(self, url: str) -> None:
        # STUB: BRW-02
        self._tabs[0].update(url=url, title=url)

    async def list_tabs(self) -> list[dict]:
        # STUB: BRW-02
        return [dict(t) for t in self._tabs]

    async def switch_tab(self, index: int) -> None:
        # STUB: BRW-02
        return None

    async def close_tab(self, index: int) -> None:
        # STUB: BRW-02
        return None

    async def go_back(self) -> None:
        # STUB: BRW-02
        return None

    async def refocus_console(self) -> None:
        # STUB: BRW-02
        return None

    async def close(self) -> None:
        # STUB: BRW-02
        return None
