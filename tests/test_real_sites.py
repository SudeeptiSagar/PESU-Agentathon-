"""BRW-06: perception on real sites. Needs the internet; runs only with RUN_NETWORK_TESTS=1.

Headless Chromium, like the test suite. DuckDuckGo blocks headless (403) but works headed, so
search is checked on Bing here; scripts/real_site_check.py --headed covers DuckDuckGo.
Findings: docs/REAL_SITE_NOTES.md.
"""
import os
from urllib.parse import quote_plus

import pytest

pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright  # noqa: E402

from app.humancheck import challenge_present  # noqa: E402
from app.perception import main_text, snapshot  # noqa: E402
from app.session import Session  # noqa: E402

pytestmark = pytest.mark.skipif(os.getenv("RUN_NETWORK_TESTS") != "1",
                                reason="set RUN_NETWORK_TESTS=1 to hit real sites")


@pytest.fixture
async def page():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        yield await (await browser.new_context()).new_page()
        await browser.close()


async def goto(page, url):
    """The Hindu's pages sometimes start their own navigation and abort ours: retry once."""
    try:
        return await page.goto(url, wait_until="domcontentloaded", timeout=40000)
    except Exception as e:
        if "ERR_ABORTED" not in str(e):
            raise
        await page.wait_for_timeout(1000)
        return await page.goto(url, wait_until="domcontentloaded", timeout=40000)


async def read(page, url):
    response = await goto(page, url)
    await page.wait_for_timeout(1500)
    assert response and response.status < 400, f"{url} answered {response and response.status}"
    snap = await snapshot(page, Session())
    assert len(snap["links"]) + len(snap["buttons"]) + len(snap["fields"]) + len(snap["tabs"]) <= 60
    assert await challenge_present(page) is None
    return snap, await main_text(page)


async def test_the_hindu_top_headline_and_article(page):
    snap, text = await read(page, "https://www.thehindu.com/")
    assert snap["headings"] and text.startswith(snap["headings"][0][:40].rstrip("…"))   # lead story first
    article = await page.evaluate("""() => { const a = Array.from(document.querySelectorAll('a[href$=".ece"]'))
        .find(a => a.innerText.trim().length > 30); return a && a.href; }""")
    page = await page.context.new_page()   # a fresh tab, away from the home page's own scripts
    snap, text = await read(page, article)
    assert text.startswith(snap["headings"][0][:40].rstrip("…")) and len(text) > 500
    assert "Subscribe Now" not in text


async def test_gov_in_portal_has_links_not_flagged(page):
    snap, text = await read(page, "https://socialjustice.gov.in/")
    assert len(snap["links"]) > 10 and text
    assert not [b for b in snap["buttons"] if b["irreversible"]]   # notices mentioning "post" stay links


async def test_bing_results_page(page):
    snap, text = await read(page, f"https://www.bing.com/search?q={quote_plus('where was Kalpana Chawla born')}")
    assert "Kalpana Chawla" in text and len(text) > 500
