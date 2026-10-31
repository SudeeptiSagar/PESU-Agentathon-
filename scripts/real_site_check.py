"""BRW-06: run perception on real sites and report what works and what is blocked.

For each site, in Playwright's Chromium (headless and/or headed): HTTP status, whether the page
looks blocked, snapshot size and time, whether main_text starts with the page's main heading and
leaves out menus, and what humancheck says. Results go into docs/REAL_SITE_NOTES.md by hand.

Run from the repo root:  python scripts/real_site_check.py [--headed] [--headless]
(default: both). Public pages only; nothing is signed in.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.async_api import async_playwright  # noqa: E402

from app.humancheck import challenge_present  # noqa: E402
from app.perception import main_text, snapshot  # noqa: E402
from app.session import Session  # noqa: E402

QUERY = "where was Kalpana Chawla born"
# (name, url, words that must not appear in main_text because they are site chrome)
SITES = [
    ("Wikipedia article", "https://en.wikipedia.org/wiki/Kalpana_Chawla",
     ("Jump to content", "Create account", "View history", "Main page")),
    ("The Hindu home", "https://www.thehindu.com/", ()),
    ("The Hindu top article", "THE_HINDU_TOP", ("Subscribe Now", "e-Paper", "Sign in")),
    ("socialjustice.gov.in", "https://socialjustice.gov.in/", ("Skip to main content", "Screen Reader Access")),
    ("DuckDuckGo results", f"https://html.duckduckgo.com/html/?q={quote_plus(QUERY)}", ()),
    ("Bing results", f"https://www.bing.com/search?q={quote_plus(QUERY)}", ()),
]
BLOCK_WORDS = ("access denied", "captcha", "unusual traffic", "are you a robot", "verify you are human", "forbidden")


async def goto(page, url):
    """Some pages (The Hindu) start their own navigation and abort ours: retry once."""
    try:
        return await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        if "ERR_ABORTED" not in str(e):
            raise
        await page.wait_for_timeout(1000)
        return await page.goto(url, wait_until="domcontentloaded", timeout=30000)


async def top_hindu_article(page) -> str | None:
    """First article link on The Hindu home page (URLs of its stories end in .ece), read in a
    separate tab so the home page's own redirects cannot interrupt the check."""
    home = await page.context.new_page()
    try:
        await goto(home, "https://www.thehindu.com/")
        await home.wait_for_timeout(1500)
        return await home.evaluate("""() => { const a = Array.from(document.querySelectorAll('a[href$=".ece"]'))
            .find(a => a.innerText.trim().length > 30); return a ? a.href : null; }""")
    finally:
        await home.close()


async def check(page, name: str, url: str, chrome_words) -> dict:
    row = {"site": name}
    try:
        if url == "THE_HINDU_TOP":
            url = await top_hindu_article(page)
            if not url:
                return {**row, "error": "no article link found"}
        t0 = time.monotonic()
        response = await goto(page, url)
        await page.wait_for_timeout(1500)
        row["status"] = response.status if response else None
        row["load_s"] = round(time.monotonic() - t0, 1)
        title = (await page.title()).lower()
        body_start = (await page.evaluate("() => document.body ? document.body.innerText.slice(0, 2000) : ''")).lower()
        row["blocked"] = (row["status"] or 0) >= 400 or any(w in title or w in body_start for w in BLOCK_WORDS)

        t0 = time.monotonic()
        snap = await snapshot(page, Session())
        row["snapshot_s"] = round(time.monotonic() - t0, 2)
        row["snapshot_chars"] = len(json.dumps(snap))
        row["counts"] = {k: len(snap[k]) for k in ("fields", "buttons", "links", "tabs")}
        row["irreversible"] = [b["text"] for b in snap["buttons"] if b["irreversible"]][:4]
        row["h1"] = snap["headings"][0] if snap["headings"] else ""

        text = await main_text(page)
        row["main_text_chars"] = len(text)
        row["starts_with_h1"] = bool(row["h1"]) and text.startswith(row["h1"][:40].rstrip("…"))
        row["chrome_leaks"] = [w for w in chrome_words if w in text]
        row["main_text_start"] = text[:160].replace("\n", " | ")
        row["humancheck"] = await challenge_present(page)
        if "results" in name:
            row["result_links"] = await page.locator(
                "a.result__a, [data-testid=result-title-a], li.b_algo h2 a").count()
    except Exception as e:
        row["error"] = " ".join(str(e).split())[:160]
    return row


async def main(modes: list[str]) -> None:
    async with async_playwright() as p:
        for mode in modes:
            browser = await p.chromium.launch(headless=(mode == "headless"))
            print(f"===== {mode}")
            for name, url, chrome_words in SITES:
                context = await browser.new_context()
                page = await context.new_page()
                print(json.dumps(await check(page, name, url, chrome_words), ensure_ascii=False))
                await context.close()
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    modes = [m for m, on in (("headless", args.headless), ("headed", args.headed)) if on] or ["headless", "headed"]
    asyncio.run(main(modes))
