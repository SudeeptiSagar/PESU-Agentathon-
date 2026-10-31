"""CORE-09: resolving what the user or LLM calls a destination."""
import json
from types import SimpleNamespace

import pytest

from app import config
from app.session import Session
from app.tools import (FILLER_WORDS, ToolExecutor, _load_sites, _site_index, normalize_phrase,
                       resolve_target)


def ok(result, kind, domain, site_id=None, trusted=False):
    assert result["kind"] == kind and result["domain"] == domain
    assert result["site_id"] == site_id and result["trusted"] is trusted
    assert result["url"]


# ---------------------------------------------------------------- the five phrasings the ticket asks for
def test_phrasing_1_a_site_name_with_filler_words():
    r = resolve_target("open the pension portal please")
    ok(r, "site", "localhost", "demo_portal", trusted=True)
    assert r["url"] == "http://localhost:8000/portal/index.html"


def test_phrasing_2_take_me_to_a_news_site():
    ok(resolve_target("Take me to the Hindu newspaper"), "site", "www.thehindu.com", "the_hindu")
    ok(resolve_target("go to wikipedia"), "site", "en.wikipedia.org", "wikipedia")


def test_phrasing_3_my_mail_is_gmail_and_untrusted():
    for phrase in ("open my gmail", "my email", "my inbox", "Google Mail", "the mail"):
        ok(resolve_target(phrase), "site", "mail.google.com", "gmail")


def test_phrasing_4_a_full_url_keeps_its_path_and_matches_a_known_site():
    r = resolve_target("https://en.wikipedia.org/wiki/Kalpana_Chawla")
    ok(r, "url", "en.wikipedia.org", "wikipedia")
    assert r["url"] == "https://en.wikipedia.org/wiki/Kalpana_Chawla"
    unknown = resolve_target("HTTPS://Example.ORG/Path?q=1")
    ok(unknown, "url", "example.org")
    assert unknown["url"] == "HTTPS://Example.ORG/Path?q=1"


def test_phrasing_5_a_bare_domain_gets_https_and_localhost_gets_http():
    r = resolve_target("wikipedia.org")
    ok(r, "domain", "wikipedia.org")
    assert r["url"] == "https://wikipedia.org"
    r = resolve_target("www.example.com/some/page?x=1")
    ok(r, "domain", "www.example.com")
    assert r["url"] == "https://www.example.com/some/page?x=1"
    r = resolve_target("localhost:8000/portal/apply.html")
    ok(r, "domain", "localhost", trusted=True)                  # trusted: localhost is the mock site
    assert r["url"] == "http://localhost:8000/portal/apply.html"
    ok(resolve_target("127.0.0.1:8000/web/search.html"), "domain", "127.0.0.1")


def test_a_gov_in_alias_beats_the_domain_reading():
    ok(resolve_target("gov.in"), "site", "socialjustice.gov.in", "social_justice")


# ---------------------------------------------------------------- not a destination: use web_search
@pytest.mark.parametrize("text", [
    "kalpana chawla birthplace", "pension portal desktop app", "where was she born", "open the",
    "", "   ", "shop for batteries on amazon", "news about floods", "readme", "3.14",
])
def test_anything_else_is_unresolved_so_the_agent_searches(text):
    r = resolve_target(text)
    assert r == {"url": None, "domain": None, "site_id": None, "trusted": False, "kind": "search"}


@pytest.mark.parametrize("text", [
    "javascript:alert(1)", "file:///C:/secret.txt", "ftp://files.example/x", "chrome://settings",
    "data:text/html,<h1>x</h1>", "about:blank", "view-source:http://x.example",
])
def test_non_web_schemes_are_not_resolved(text):
    assert resolve_target(text)["url"] is None


@pytest.mark.parametrize("text", [
    "https://google.com@evil.example/login",            # looks like google.com, goes to evil.example
    "https://user:pass@example.org/", "http://host.example:99999/", "http://host.example:abc/",
    "https://", "http:///nohost", "x" * 2001,
])
def test_spoofed_or_malformed_addresses_are_not_resolved(text):
    assert resolve_target(text)["url"] is None


def test_a_host_with_a_username_is_not_confused_with_a_bare_domain():
    assert resolve_target("google.com@evil.example")["url"] is None


def test_trust_comes_from_sites_json_not_from_the_wording():
    assert resolve_target("https://mail.google.com/mail/u/0/#inbox")["trusted"] is False
    assert resolve_target("pension portal")["trusted"] is True
    assert resolve_target("https://localhost.evil.example/")["trusted"] is False


# ---------------------------------------------------------------- the helpers
@pytest.mark.parametrize("text,expected", [
    ("Open the Pension Portal!", "pension portal"), ("my_mail", "mail"), ("  GO TO   wiki, please ", "wiki"),
    ("gov.in", "gov.in"), ("the Hindu.", "hindu"), ("", ""), ("open the", ""),
])
def test_normalize_phrase(text, expected):
    assert normalize_phrase(text) == expected


def test_filler_words_are_lowercase_plain_words():
    assert all(w == w.lower() and w.isalpha() for w in FILLER_WORDS)


def test_no_two_sites_claim_the_same_spoken_name():
    claimed: dict[str, str] = {}
    for site in _load_sites():
        for name in [site["id"], *site["aliases"]]:
            key = normalize_phrase(name)
            assert key, f"{name!r} is nothing but filler words"
            assert claimed.setdefault(key, site["id"]) == site["id"], f"{name!r} is claimed twice"
    assert set(claimed) == set(_site_index())


def test_a_site_directory_that_cannot_be_read_just_resolves_urls(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SITES_PATH", tmp_path / "missing.json")
    assert resolve_target("wikipedia")["url"] is None
    ok(resolve_target("https://example.org/"), "url", "example.org")
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(config, "SITES_PATH", bad)
    assert resolve_target("wiki")["url"] is None


def test_a_site_with_a_clash_keeps_the_first_entry(monkeypatch, tmp_path):
    path = tmp_path / "sites.json"
    path.write_text(json.dumps([
        {"id": "a", "aliases": ["shop"], "url": "https://a.example", "domain": "a.example", "trusted": False},
        {"id": "b", "aliases": ["the shop"], "url": "https://b.example", "domain": "b.example", "trusted": False}]),
        encoding="utf-8")
    monkeypatch.setattr(config, "SITES_PATH", path)
    assert resolve_target("shop")["site_id"] == "a"


# ---------------------------------------------------------------- through the navigate tool
class Page:
    url = "about:blank"


class Browser:
    def __init__(self):
        self.active, self.visited = Page(), []

    async def goto(self, url):
        self.visited.append(url)
        self.active.url = url


async def test_navigate_opens_a_spoken_site_name_and_announces_its_domain():
    heard, browser = [], Browser()
    ex = ToolExecutor(announce=heard.append)
    result = await ex.run({"name": "navigate", "args": {"target": "open my gmail"}}, Session(), browser)
    assert result.startswith("ok:") and browser.visited == ["https://mail.google.com/mail/u/0/#inbox"]
    assert heard == ["mail.google.com"]


async def test_navigate_to_an_unknown_name_sends_the_agent_to_web_search():
    browser = Browser()
    result = await ToolExecutor().run(
        {"name": "navigate", "args": {"target": "kalpana chawla birthplace"}}, Session(), browser)
    assert result.startswith("error:") and "web_search" in result and browser.visited == []


async def test_navigate_to_a_bare_domain_and_a_blocked_one(monkeypatch):
    monkeypatch.setattr(config, "BLOCKED_DOMAINS", {"evil.example"})
    browser, ex = Browser(), ToolExecutor()
    assert (await ex.run({"name": "navigate", "args": {"target": "example.org"}}, Session(), browser)).startswith("ok:")
    assert browser.visited == ["https://example.org"]
    blocked = await ex.run({"name": "navigate", "args": {"target": "login.evil.example"}}, Session(), browser)
    assert blocked.startswith("blocked:") and browser.visited == ["https://example.org"]
    spoof = await ex.run({"name": "navigate", "args": {"target": "https://google.com@evil.example/"}}, Session(), browser)
    assert spoof.startswith("error:") and browser.visited == ["https://example.org"]
