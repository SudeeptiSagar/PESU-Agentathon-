"""BRW-05: app/sites.json is valid, covers the required sites, and resolves through tools.resolve_target."""
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from app import config
from app.tools import resolve_target

SITES = json.loads(Path(config.SITES_PATH).read_text(encoding="utf-8"))
MOCK_SITE = Path(__file__).resolve().parent.parent / "mock_site"


def test_entries_are_well_formed():
    assert isinstance(SITES, list) and SITES
    for site in SITES:
        assert {"id", "aliases", "url", "domain", "trusted"} <= set(site), site
        assert isinstance(site["trusted"], bool)
        assert site["aliases"] and all(a == a.strip().lower() and a for a in site["aliases"]), site["id"]
        assert urlparse(site["url"]).hostname == site["domain"], site["id"]


def test_ids_and_aliases_are_unique():
    ids = [s["id"] for s in SITES]
    aliases = [a for s in SITES for a in s["aliases"]]
    assert len(ids) == len(set(ids))
    assert len(aliases) == len(set(aliases)), "an alias would resolve to two sites"
    for site in SITES:
        for other in SITES:
            if other is not site:
                assert site["id"] not in other["aliases"], f'{site["id"]} is also an alias of {other["id"]}'


def test_required_sites_are_present():
    ids = {s["id"] for s in SITES}
    # Mock portal, shop, search (+ inbox), and 4 real sites: Wikipedia, news, gov.in, DuckDuckGo.
    assert {"demo_portal", "demo_shop", "demo_search", "demo_mail", "wikipedia", "duckduckgo", "gmail"} <= ids
    domains = {s["domain"] for s in SITES}
    assert any(d.endswith(".gov.in") for d in domains)
    assert "www.thehindu.com" in domains


def test_only_local_mocks_are_trusted():
    # trusted=true lets the agent type profile values without asking (hard rule 3).
    for site in SITES:
        if site["trusted"]:
            assert site["domain"] == "localhost", site["id"]


def test_gmail_aliases_are_untrusted():
    for alias in ("gmail", "my mail"):
        target = resolve_target(alias)
        assert target["site_id"] == "gmail" and target["domain"] == "mail.google.com"
        assert target["trusted"] is False


@pytest.mark.parametrize("alias,site_id", [("pension portal", "demo_portal"), ("Demo Shop", "demo_shop"),
                                          ("mock search", "demo_search"), ("wiki", "wikipedia"),
                                          ("the hindu", "the_hindu"), ("social justice", "social_justice"),
                                          ("duck duck go", "duckduckgo")])
def test_aliases_resolve(alias, site_id):
    assert resolve_target(alias)["site_id"] == site_id


def test_mock_urls_exist_on_disk():
    for site in SITES:
        if site["domain"] == "localhost":
            path = urlparse(site["url"]).path.lstrip("/")
            assert (MOCK_SITE / path).is_file(), site["url"]
