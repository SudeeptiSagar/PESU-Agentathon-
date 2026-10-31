"""CORE-08: tool executor, placeholder substitution, domain policy and the irreversible hold."""
import copy
import functools
import http.server
import inspect
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote_plus

import pytest

from app import config, perception, tools
from app.profile import DEMO_PROFILE
from app.session import IllegalTransition, Session, confirm, transition
from app.tools import (TOOL_NAMES, TOOL_SCHEMAS, ToolExecutor, approve_domain, commit_pending,
                       domain_allowed, parse_result, record_snapshot, scrub_sensitive)

AADHAAR = DEMO_PROFILE["aadhaar"]
FORM_URL = "http://example.org/apply"          # not trusted: profile values need approval
PORTAL_URL = "http://localhost:8000/portal/apply.html"   # trusted in sites.json

SNAP = {
    "fields": [
        {"id": "f1", "label": "Full name", "type": "text", "sensitive_hint": False},
        {"id": "f2", "label": "Date of birth", "type": "date", "sensitive_hint": False},
        {"id": "f3", "label": "Gender", "type": "select", "sensitive_hint": False},
        {"id": "f4", "label": "Aadhaar number", "type": "text", "sensitive_hint": True},
        {"id": "f5", "label": "Account password", "type": "password", "sensitive_hint": True},
        {"id": "f6", "label": "Enter the OTP sent to you", "type": "text", "sensitive_hint": True},
    ],
    "tabs": [{"id": "t1", "text": "Bank Details", "selected": False}],
    "links": [{"id": "l1", "text": "Help"}],
    "buttons": [
        {"id": "b1", "text": "Submit application", "irreversible": True, "kind": "submit"},
        {"id": "b2", "text": "Next: Bank Details", "irreversible": False, "kind": "other"},
        {"id": "b3", "text": "Confirm", "irreversible": False, "kind": "other"},   # stale flag
    ],
}


# ---------------------------------------------------------------- fakes
class FakeLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    async def fill(self, value, timeout=None):
        if self.page.fill_error:
            raise self.page.fill_error
        self.page.calls.append(("fill", self.selector, value))

    async def select_option(self, **kw):
        self.page.calls.append(("select", self.selector, kw))

    async def click(self, timeout=None):
        self.page.calls.append(("click", self.selector))

    async def count(self):
        return self.page.counts.get(self.selector, 1)

    async def evaluate(self, js):
        return self.page.stable.get(self.selector)


class FakePage:
    def __init__(self, url=PORTAL_URL):
        self.url, self.calls, self.counts, self.stable, self.fill_error = url, [], {}, {}, None
        self.guard = {"activeId": None, "inForm": False, "ids": [], "untagged": 0, "search": False,
                      "method": None}
        self.keyboard = SimpleNamespace(press=self._press)

    def locator(self, selector):
        return FakeLocator(self, selector)

    async def evaluate(self, js, arg=None):
        if "activeElement" in js:
            return self.guard
        self.calls.append(("evaluate", arg))

    async def _press(self, key):
        self.calls.append(("press", key))

    async def wait_for_load_state(self, *a, **k):
        pass

    def clicks(self):
        return [c for c in self.calls if c[0] == "click"]


class FakeBrowser:
    def __init__(self, page):
        self.active, self.visited, self.tabs = page, [], 2
        self.redirect_to = None

    async def goto(self, url):
        self.visited.append(url)
        self.active.url = self.redirect_to or url

    async def go_back(self):
        self.visited.append("<back>")

    async def switch_tab(self, index):
        if not 0 <= index < self.tabs:
            raise IndexError(f"No tab {index}; there are {self.tabs} tabs")

    async def close_tab(self, index):
        await self.switch_tab(index)


@pytest.fixture
def setup():
    def make(url=PORTAL_URL):
        session = Session(profile=copy.deepcopy(DEMO_PROFILE))
        session.locators = {k: f'[data-agent-id="{k}"]' for k in
                            ("f1", "f2", "f3", "f4", "f5", "f6", "t1", "l1", "b1", "b2", "b3")}
        record_snapshot(session, SNAP)
        page = FakePage(url)
        page.stable = {'[data-agent-id="f1"]': "#full_name", '[data-agent-id="f2"]': "#dob"}
        return ToolExecutor(), session, FakeBrowser(page), page
    return make


def act(name, **args):
    return {"name": name, "args": args}


# ---------------------------------------------------------------- no submit tool (hard rule 2)
def test_no_submit_or_commit_tool_and_executor_cannot_reach_commit():
    assert not {n for n in TOOL_NAMES if "submit" in n or "commit" in n}
    assert len(TOOL_SCHEMAS) == 15 and TOOL_NAMES == {t["function"]["name"] for t in TOOL_SCHEMAS}
    assert "commit_pending" not in inspect.getsource(ToolExecutor)


@pytest.mark.parametrize("name", ["submit_form", "commit_pending", "submit", "commit", "", None, 5])
async def test_unknown_or_forbidden_tool_names_do_nothing(setup, name):
    ex, session, browser, page = setup()
    result = await ex.run({"name": name, "args": {}}, session, browser)
    assert result.startswith("error: unknown tool") and page.calls == []


async def test_bad_action_shapes(setup):
    ex, session, browser, page = setup()
    assert (await ex.run({"name": "click", "args": "b1"}, session, browser)).startswith("error")
    assert (await ex.run("click", session, browser)).startswith("error")
    assert page.calls == []


# ---------------------------------------------------------------- placeholders (hard rule 1)
async def test_fill_field_substitutes_the_placeholder_and_never_echoes_the_value(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    result = await ex.run(act("fill_field", field_id="f1", value_ref="{full_name}"), session, browser)
    assert result.startswith("ok:") and DEMO_PROFILE["full_name"] not in result
    assert ("fill", '[data-agent-id="f1"]', DEMO_PROFILE["full_name"]) in page.calls


async def test_expected_value_is_recorded_with_type_selector_and_source(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    await ex.run(act("fill_field", field_id="f2", value_ref="{dob}"), session, browser)
    assert session.expected["f2"] == {
        "label": "Date of birth", "selector": "#dob", "value": DEMO_PROFILE["dob"], "type": "date",
        "source": "profile:dob", "url": PORTAL_URL}
    await ex.run(act("fill_field", field_id="f4", value_ref="{aadhaar}"), session, browser)
    assert session.expected["f4"]["type"] == "aadhaar"
    assert session.expected["f4"]["selector"] == '[data-agent-id="f4"]'   # no stable id: falls back


@pytest.mark.parametrize("ref", ["{nope}", "dob", "My {dob}", "{dob} {dob}", "", "{}", "{DOB}", "$dob"])
async def test_only_exact_known_placeholders_are_accepted(setup, ref):
    ex, session, browser, page = setup(PORTAL_URL)
    result = await ex.run(act("fill_field", field_id="f1", value_ref=ref), session, browser)
    assert result.startswith("error:") and page.calls == []


async def test_missing_profile_key_asks_instead_of_guessing(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    del session.profile["dob"]
    result = await ex.run(act("fill_field", field_id="f2", value_ref="{dob}"), session, browser)
    assert result.startswith("error:") and "no dob" in result and page.calls == []


async def test_type_text_refuses_placeholders(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    result = await ex.run(act("type_text", field_id="f1", text="Hello {full_name}"), session, browser)
    assert result.startswith("error:") and "fill_field" in result and page.calls == []


# ---------------------------------------------------------------- domain approval (hard rule 3)
async def test_profile_values_need_approval_on_an_untrusted_domain(setup):
    ex, session, browser, page = setup(FORM_URL)
    result = await ex.run(act("fill_field", field_id="f1", value_ref="{full_name}"), session, browser)
    assert result == "needs_approval: example.org" and page.calls == []
    approve_domain(session, "Example.ORG.")
    result = await ex.run(act("fill_field", field_id="f1", value_ref="{full_name}"), session, browser)
    assert result.startswith("ok:") and len(page.calls) == 1


async def test_trusted_sites_json_domain_needs_no_approval(setup):
    ex, session, browser, page = setup("http://localhost:8000/portal/apply.html")
    result = await ex.run(act("fill_field", field_id="f1", value_ref="{full_name}"), session, browser)
    assert result.startswith("ok:")


async def test_approval_is_per_domain_and_per_session(setup):
    ex, session, browser, page = setup(FORM_URL)
    approve_domain(session, "example.org")
    page.url = "http://other.example.net/form"
    assert (await ex.run(act("fill_field", field_id="f1", value_ref="{full_name}"),
                         session, browser)).startswith("needs_approval")
    fresh = Session(profile=copy.deepcopy(DEMO_PROFILE))
    assert fresh.approved_domains == set()


async def test_select_option_with_a_placeholder_also_needs_approval(setup):
    ex, session, browser, page = setup(FORM_URL)
    assert (await ex.run(act("select_option", field_id="f3", option="{gender}"),
                         session, browser)) == "needs_approval: example.org"
    approve_domain(session, "example.org")
    assert (await ex.run(act("select_option", field_id="f3", option="{gender}"),
                         session, browser)).startswith("ok:")
    assert ("select", '[data-agent-id="f3"]', {"label": "male", "timeout": 5000}) in page.calls
    assert session.expected["f3"]["source"] == "profile:gender" and session.expected["f3"]["type"] == "select"


async def test_plain_text_needs_no_approval_but_a_sensitive_value_typed_as_text_does(setup):
    ex, session, browser, page = setup(FORM_URL)
    assert (await ex.run(act("type_text", field_id="f1", text="Kalpana Chawla"), session, browser)).startswith("ok:")
    for sneaky in (AADHAAR, "0000 1111 2222", "0000-1111-2222"):
        result = await ex.run(act("type_text", field_id="f1", text=sneaky), session, browser)
        assert result == "needs_approval: example.org", sneaky
    assert [c for c in page.calls if c[0] == "fill"] == [("fill", '[data-agent-id="f1"]', "Kalpana Chawla")]


# ---------------------------------------------------------------- humans do the human parts (rule 6)
@pytest.mark.parametrize("field_id", ["f5", "f6"])
@pytest.mark.parametrize("tool,args", [
    ("type_text", {"text": "hunter2"}),
    ("fill_field", {"value_ref": "{full_name}"}),
    ("select_option", {"option": "x"}),
])
async def test_passwords_and_codes_are_never_typed(setup, field_id, tool, args):
    ex, session, browser, page = setup(PORTAL_URL)
    result = await ex.run(act(tool, field_id=field_id, **args), session, browser)
    assert result.startswith("needs_human:") and page.calls == []


async def test_dropdown_needs_select_option(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    result = await ex.run(act("fill_field", field_id="f3", value_ref="{gender}"), session, browser)
    assert result.startswith("error:") and "select_option" in result


# ---------------------------------------------------------------- no sensitive values in results (rule 4)
def test_scrub_sensitive():
    p = DEMO_PROFILE
    for text in (f"id {AADHAAR}!", "id 0000 1111 2222!", "id 0000-1111-2222!", f"id {AADHAAR[:4]} {AADHAAR[4:]}!"):
        assert "[hidden]" in scrub_sensitive(text, p) and "1111" not in scrub_sensitive(text, p)
    assert scrub_sensitive(f"ifsc {p['ifsc'].lower()} acct {p['bank_account']}", p) == "ifsc [hidden] acct [hidden]"
    assert scrub_sensitive("Ramesh Kumar 560001 9876543210", p) == "Ramesh Kumar 560001 9876543210"
    assert scrub_sensitive("abc", {"aadhaar": "12"}) == "abc"           # too short to scrub
    assert scrub_sensitive("abc", {}) == "abc"


async def test_errors_and_page_text_are_scrubbed(setup, monkeypatch):
    ex, session, browser, page = setup(PORTAL_URL)
    page.fill_error = RuntimeError(f"Locator.fill: Timeout. fill('{AADHAAR}')\nCall log: more")
    result = await ex.run(act("fill_field", field_id="f1", value_ref="{full_name}"), session, browser)
    assert result.startswith("error: RuntimeError") and AADHAAR not in result and "Call log" not in result

    async def main_text(p, max_chars=4000):
        return "Your Aadhaar is 0000 1111 2222 and IFSC TEST0000001"
    monkeypatch.setattr(perception, "main_text", main_text)
    result = await ex.run(act("read_page", mode="main_text"), session, browser)
    assert "1111" not in result and "TEST0000001" not in result and "untrusted" in result


def test_session_repr_does_not_reveal_the_profile_or_expected_values():
    s = Session(profile={"aadhaar": AADHAAR}, expected={"f1": {"value": AADHAAR}})
    assert AADHAAR not in repr(s) and AADHAAR not in str(s)


# ---------------------------------------------------------------- irreversible hold (hard rule 2)
async def test_irreversible_click_is_held_not_clicked(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    result = await ex.run(act("click", element_id="b1"), session, browser)
    assert result.startswith("held:") and "NOT pressed" in result and page.clicks() == []
    assert session.pending_action == {
        "element_id": "b1", "label": "Submit application", "kind": "submit", "url": PORTAL_URL,
        "domain": "localhost", "selector": '[data-agent-id="b1"]'}


async def test_text_check_holds_a_button_whose_flag_is_missing(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    result = await ex.run(act("click", element_id="b3"), session, browser)   # "Confirm", flagged False
    assert result.startswith("held:") and page.clicks() == []


async def test_normal_click_runs_and_old_ids_stop_working(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    assert (await ex.run(act("click", element_id="b2"), session, browser)) == "ok: clicked 'Next: Bank Details'"
    assert page.clicks() == [("click", '[data-agent-id="b2"]')] and session.pending_action is None
    again = await ex.run(act("click", element_id="b2"), session, browser)
    assert again.startswith("error:") and "read the page again" in again and len(page.clicks()) == 1


@pytest.mark.parametrize("element_id", ["b99", "", "f1", "zzz"])
async def test_unknown_or_non_clickable_ids(setup, element_id):
    ex, session, browser, page = setup(PORTAL_URL)
    result = await ex.run(act("click", element_id=element_id), session, browser)
    if element_id == "f1":                                  # a field can be clicked (focus); it is not held
        assert result.startswith("ok:")
    else:
        assert result.startswith("error:") and page.clicks() == []


async def test_an_id_the_executor_never_saw_is_not_clickable_even_if_a_locator_exists(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    session.locators["b7"] = '[data-agent-id="b7"]'
    assert (await ex.run(act("click", element_id="b7"), session, browser)).startswith("error:")
    assert page.clicks() == []


# ---------------------------------------------------------------- keys
@pytest.mark.parametrize("key", ["Control+Enter", "Meta+Enter", "Shift+Enter", "a", "#", "Delete",
                                 "Backspace", "F5", "Alt+ArrowLeft", "Control+w", "Enter Enter"])
async def test_dangerous_keys_are_refused(setup, key):
    ex, session, browser, page = setup(PORTAL_URL)
    assert (await ex.run(act("press_key", key=key), session, browser)).startswith("error:")
    assert page.calls == []


@pytest.mark.parametrize("raw,sent", [("tab", "Tab"), ("Escape", "Escape"), ("down", "ArrowDown"),
                                      ("PageDown", "PageDown"), ("Shift+Tab", "Shift+Tab")])
async def test_safe_keys_are_pressed(setup, raw, sent):
    ex, session, browser, page = setup(PORTAL_URL)
    assert (await ex.run(act("press_key", key=raw), session, browser)) == f"ok: pressed {sent}"
    assert page.calls == [("press", sent)]


async def test_enter_is_refused_when_it_would_submit_an_irreversible_form(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    page.guard.update(inForm=True, ids=["b1"], method="get")
    result = await ex.run(act("press_key", key="Enter"), session, browser)
    assert result.startswith("error:") and "click its submit button" in result and page.calls == []


async def test_enter_is_refused_on_a_focused_irreversible_button_and_space_too(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    page.guard.update(activeId="b1")
    for key in ("Enter", "Space"):
        assert (await ex.run(act("press_key", key=key), session, browser)).startswith("error:")
    assert page.calls == []


async def test_enter_is_refused_on_unknown_default_buttons_but_not_in_search_boxes(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    page.guard.update(inForm=True, untagged=1, method="get")
    assert (await ex.run(act("press_key", key="Enter"), session, browser)).startswith("error:")
    page.guard.update(inForm=True, ids=[], untagged=0, method="post")
    assert (await ex.run(act("press_key", key="Enter"), session, browser)).startswith("error:")
    page.guard.update(inForm=True, ids=["b2"], untagged=0, method="post", search=False)
    assert (await ex.run(act("press_key", key="Enter"), session, browser)).startswith("ok:")
    page.calls.clear()
    page.guard.update(inForm=True, ids=[], untagged=1, search=True, method="get")
    assert (await ex.run(act("press_key", key="Enter"), session, browser)).startswith("ok:")
    assert ("press", "Enter") in page.calls


async def test_enter_outside_any_form_is_fine(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    assert (await ex.run(act("press_key", key="Enter"), session, browser)).startswith("ok:")


# ---------------------------------------------------------------- navigation and domain policy
async def test_blocked_domains_and_subdomains(setup, monkeypatch):
    monkeypatch.setattr(config, "BLOCKED_DOMAINS", {"evil.example"})
    assert domain_allowed("good.example") and not domain_allowed("EVIL.example.")
    assert not domain_allowed("www.evil.example") and domain_allowed("notevil.example")
    ex, session, browser, page = setup(PORTAL_URL)
    for target in ("https://evil.example/x", "www.evil.example", "evil.example"):
        result = await ex.run(act("navigate", target=target), session, browser)
        assert result.startswith("blocked:"), target
    assert browser.visited == []
    result = await ex.run(act("web_search", query="x"), session, browser)
    assert result.startswith("ok:")                         # the search engine itself is allowed


async def test_search_engine_on_the_blocklist_is_blocked(setup, monkeypatch):
    monkeypatch.setattr(config, "BLOCKED_DOMAINS", {"duckduckgo.com"})
    monkeypatch.setattr(config, "SEARCH_URL", "https://html.duckduckgo.com/html/?q={q}")
    ex, session, browser, page = setup(PORTAL_URL)
    assert (await ex.run(act("web_search", query="x"), session, browser)).startswith("blocked:")
    assert browser.visited == []


async def test_a_redirect_to_a_blocked_domain_is_left_at_once(setup, monkeypatch):
    monkeypatch.setattr(config, "BLOCKED_DOMAINS", {"evil.example"})
    ex, session, browser, page = setup(PORTAL_URL)
    browser.redirect_to = "https://evil.example/landing"
    result = await ex.run(act("navigate", target="https://good.example/start"), session, browser)
    assert result.startswith("blocked: evil.example") and browser.visited[-1] == "about:blank"


@pytest.mark.parametrize("target", ["javascript:alert(1)", "JAVASCRIPT:alert(1)", "file:///C:/secret.txt",
                                    "data:text/html,<h1>x</h1>", "chrome://settings", "about:blank",
                                    "view-source:http://x", "ftp://host/file"])
async def test_non_web_addresses_are_refused(setup, target):
    ex, session, browser, page = setup(PORTAL_URL)
    assert (await ex.run(act("navigate", target=target), session, browser)).startswith("error:")
    assert browser.visited == []


async def test_alias_resolves_through_sites_json(setup):
    ex, session, browser, page = setup(FORM_URL)
    result = await ex.run(act("navigate", target="demo portal"), session, browser)
    assert result.startswith("ok:") and browser.visited == ["http://localhost:8000/portal/index.html"]


async def test_each_new_domain_is_announced_once(setup):
    heard = []
    ex, session, browser, page = setup(FORM_URL)
    ex.announce = heard.append
    await ex.run(act("navigate", target="https://a.example/1"), session, browser)
    await ex.run(act("navigate", target="https://a.example/2"), session, browser)
    await ex.run(act("navigate", target="https://b.example/"), session, browser)
    assert heard == ["a.example", "b.example"]


async def test_async_announce_callback(setup):
    heard = []

    async def say(domain):
        heard.append(domain)
    ex, session, browser, page = setup(FORM_URL)
    ex.announce = say
    await ex.run(act("navigate", target="https://a.example/"), session, browser)
    assert heard == ["a.example"]


async def test_web_search_builds_the_url_from_search_url(setup, monkeypatch):
    monkeypatch.setattr(config, "SEARCH_URL", "http://localhost:8000/web/search.html?q={q}")
    ex, session, browser, page = setup(FORM_URL)
    await ex.run(act("web_search", query="Kalpana Chawla & {born}"), session, browser)
    assert browser.visited == ["http://localhost:8000/web/search.html?q=" + quote_plus("Kalpana Chawla & {born}")]


async def test_navigating_away_drops_expected_values_of_the_old_page(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    await ex.run(act("fill_field", field_id="f1", value_ref="{full_name}"), session, browser)
    assert "f1" in session.expected
    await ex.run(act("navigate", target="https://a.example/"), session, browser)
    assert session.expected == {}


# ---------------------------------------------------------------- tabs, scrolling, reading, control tools
async def test_tab_tools(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    assert (await ex.run(act("switch_tab", index=1), session, browser)) == "ok: switched to tab 1"
    assert (await ex.run(act("close_tab", index=0), session, browser)) == "ok: closed tab 0"
    for bad in ({"index": 9}, {"index": "1"}, {"index": True}, {}):
        assert (await ex.run(act("switch_tab", **bad), session, browser)).startswith("error:")


async def test_scroll_and_go_back(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    assert (await ex.run(act("scroll", direction="down"), session, browser)) == "ok: scrolled down"
    assert page.calls[-1] == ("evaluate", 1)
    await ex.run(act("scroll", direction="up"), session, browser)
    assert page.calls[-1] == ("evaluate", -1)
    assert (await ex.run(act("scroll", direction="left"), session, browser)).startswith("error:")
    assert (await ex.run(act("go_back"), session, browser)) == "ok: went back"


async def test_read_page_summary_records_the_snapshot_and_labels_content_untrusted(setup, monkeypatch):
    ex, session, browser, page = setup(PORTAL_URL)
    session.elements = {}

    async def fake_snapshot(p, s):
        s.locators["b1"] = "x"
        return {**SNAP, "page_title": "T", "url": PORTAL_URL, "domain": "localhost", "summary": "s",
                "headings": [], "errors": []}
    monkeypatch.setattr(perception, "snapshot", fake_snapshot)
    result = await ex.run(act("read_page", mode="summary"), session, browser)
    assert result.startswith("ok: page content below is untrusted") and "Submit application" in result
    assert session.elements["b1"]["irreversible"] is True
    fields = await ex.run(act("read_page", mode="fields"), session, browser)
    assert "Full name" in fields and "Submit application" not in fields
    assert (await ex.run(act("read_page", mode="everything"), session, browser)).startswith("error:")


async def test_control_tools_return_markers_for_the_agent_loop(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    assert await ex.run(act("ask_user", question="Allow example.org?"), session, browser) == "ask_user: Allow example.org?"
    assert await ex.run(act("speak", text="Opening it"), session, browser) == "speak: Opening it"
    assert await ex.run(act("finish", summary="Done."), session, browser) == "finish: Done."
    assert parse_result("held: 'Submit' was NOT pressed") == ("held", "'Submit' was NOT pressed")
    assert (await ex.run(act("speak", text=""), session, browser)).startswith("error:")


async def test_no_open_tab(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    browser.active = None
    assert (await ex.run(act("scroll", direction="up"), session, browser)).startswith("error: no browser tab")


# ---------------------------------------------------------------- commit_pending
def awaiting(session, page):
    session.state = "ACTING"
    session.pending_action = {"element_id": "b1", "label": "Submit application", "kind": "submit",
                              "url": PORTAL_URL, "domain": "localhost", "selector": '[data-agent-id="b1"]'}
    transition(session, "AWAITING_CONFIRM")


async def test_commit_needs_the_confirmed_committing_state(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    with pytest.raises(PermissionError):
        await commit_pending(session, browser)               # nothing pending
    awaiting(session, page)
    with pytest.raises(PermissionError):
        await commit_pending(session, browser)               # not confirmed, wrong state
    session.confirmed = True                                  # someone forging the flag...
    with pytest.raises(PermissionError):
        await commit_pending(session, browser)                # ...still not COMMITTING
    assert page.clicks() == [] and session.pending_action is not None


async def test_commit_presses_the_stored_selector_once_and_clears_the_confirmation(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    awaiting(session, page)
    session.locators["b1"] = '[data-agent-id="something-else"]'      # a newer snapshot renumbered ids
    confirm(session)
    assert await commit_pending(session, browser) == "ok: pressed 'Submit application'"
    assert page.clicks() == [("click", '[data-agent-id="b1"]')]
    assert session.pending_action is None and session.confirmed is False
    with pytest.raises(PermissionError):
        await commit_pending(session, browser)                       # single use


async def test_commit_refuses_when_the_page_changed(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    awaiting(session, page)
    confirm(session)
    page.url = "http://localhost:8000/portal/ack.html"
    assert (await commit_pending(session, browser)).startswith("error: the page changed")
    assert page.clicks() == [] and session.pending_action is None and session.confirmed is False


async def test_commit_refuses_when_the_control_is_gone_or_ambiguous(setup):
    for count in (0, 2):
        ex, session, browser, page = setup(PORTAL_URL)
        awaiting(session, page)
        confirm(session)
        page.counts['[data-agent-id="b1"]'] = count
        assert (await commit_pending(session, browser)).startswith("error: that control")
        assert page.clicks() == []


async def test_commit_to_a_blocked_domain_is_left(setup, monkeypatch):
    monkeypatch.setattr(config, "BLOCKED_DOMAINS", {"evil.example"})
    ex, session, browser, page = setup(PORTAL_URL)
    awaiting(session, page)
    confirm(session)

    async def click(self, timeout=None):
        self.page.url = "https://evil.example/after"
    monkeypatch.setattr(FakeLocator, "click", click)
    assert (await commit_pending(session, browser)).startswith("blocked: evil.example")
    assert browser.visited[-1] == "about:blank"


async def test_holding_then_confirming_end_to_end(setup):
    ex, session, browser, page = setup(PORTAL_URL)
    session.state = "ACTING"
    assert (await ex.run(act("click", element_id="b1"), session, browser)).startswith("held:")
    transition(session, "AWAITING_CONFIRM")
    with pytest.raises(IllegalTransition):
        transition(session, "COMMITTING")                    # saying nothing is not a confirmation
    confirm(session)                                          # the user said "confirm"
    assert (await commit_pending(session, browser)).startswith("ok: pressed")
    assert len(page.clicks()) == 1


def test_record_snapshot_maps_every_element_kind():
    s = Session()
    record_snapshot(s, SNAP)
    assert s.elements["f1"] == {"kind": "field", "label": "Full name", "type": "text", "sensitive_hint": False}
    assert s.elements["b1"] == {"kind": "button", "label": "Submit application", "irreversible": True, "action": "submit"}
    assert s.elements["l1"]["kind"] == "link" and s.elements["t1"]["kind"] == "tab"


# ================================================================ real pages (headless Chromium)
pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright  # noqa: E402

MOCK_SITE = Path(__file__).resolve().parent.parent / "mock_site"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(MOCK_SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
async def real():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await (await browser.new_context()).new_page()
        yield SimpleNamespace(active=page, goto=lambda url: page.goto(url), go_back=page.go_back), page
        await browser.close()


def field_id(snap, label):
    return next(f["id"] for f in snap["fields"] if f["label"].startswith(label))


async def test_real_portal_fill_select_and_expected_values(base, real):
    browser, page = real
    await page.goto(f"{base}/portal/apply.html")
    session, ex = Session(profile=copy.deepcopy(DEMO_PROFILE)), ToolExecutor()
    snap = await tools.take_snapshot(page, session)
    name_id, gender_id = field_id(snap, "Full name"), field_id(snap, "Gender")

    unapproved = await ex.run(act("fill_field", field_id=name_id, value_ref="{full_name}"), session, browser)
    assert unapproved == "needs_approval: 127.0.0.1" and await page.input_value("#full_name") == ""

    approve_domain(session, "127.0.0.1")
    result = await ex.run(act("fill_field", field_id=name_id, value_ref="{full_name}"), session, browser)
    assert result.startswith("ok:") and DEMO_PROFILE["full_name"] not in result
    assert await page.input_value("#full_name") == DEMO_PROFILE["full_name"]
    assert session.expected[name_id]["selector"] == "#full_name"

    options = next(f for f in snap["fields"] if f["id"] == gender_id)["options"]
    pick = next(o for o in options if o.lower() == DEMO_PROFILE["gender"])
    assert (await ex.run(act("select_option", field_id=gender_id, option=pick), session, browser)).startswith("ok:")
    assert (await page.eval_on_selector(f"#{session.expected[gender_id]['selector'][1:]}", "e => e.selectedOptions[0].text")
            if session.expected[gender_id]["selector"].startswith("#") else pick) == pick


async def test_real_portal_enter_cannot_submit_the_form(base, real):
    browser, page = real
    await page.goto(f"{base}/portal/apply.html")
    session, ex = Session(profile=copy.deepcopy(DEMO_PROFILE)), ToolExecutor()
    await tools.take_snapshot(page, session)
    await page.focus("#full_name")
    result = await ex.run(act("press_key", key="Enter"), session, browser)
    assert result.startswith("error:") and "button" in result
    assert page.url.endswith("/portal/apply.html")


async def test_real_irreversible_button_is_held_then_pressed_only_after_confirm(base, real):
    browser, page = real
    await page.goto(f"{base}/web/message.html?id=4")
    session, ex = Session(profile=copy.deepcopy(DEMO_PROFILE)), ToolExecutor()
    snap = await tools.take_snapshot(page, session)
    delete = next(b for b in snap["buttons"] if b["text"] == "Delete")
    assert delete["irreversible"] and delete["kind"] == "delete"

    session.state = "ACTING"
    result = await ex.run(act("click", element_id=delete["id"]), session, browser)
    assert result.startswith("held:")
    deleted = "() => JSON.parse(localStorage.getItem('mockmail.deleted') || '[]')"
    assert await page.evaluate(deleted) == [] and "message.html" in page.url   # nothing was pressed
    assert session.pending_action["selector"]

    await tools.take_snapshot(page, session)                  # ids get renumbered by a newer snapshot
    transition(session, "AWAITING_CONFIRM")
    confirm(session)
    assert (await commit_pending(session, browser)).startswith("ok: pressed 'Delete'")
    await page.wait_for_url("**/inbox.html")                  # the mock deletes the message, then goes to the inbox
    assert await page.evaluate(deleted) == [4]                # now it was really pressed


async def test_real_search_box_allows_enter_and_a_normal_link_navigates(base, real):
    browser, page = real
    await page.goto(f"{base}/web/search.html")
    session, ex = Session(profile=copy.deepcopy(DEMO_PROFILE)), ToolExecutor()
    snap = await tools.take_snapshot(page, session)
    box = field_id(snap, "Search")
    assert (await ex.run(act("type_text", field_id=box, text="kalpana chawla"), session, browser)).startswith("ok:")
    assert (await ex.run(act("press_key", key="Enter"), session, browser)).startswith("ok:")
    await page.wait_for_url("**q=kalpana*")
    assert session.elements == {}                             # the old page's ids are gone

    await page.goto(f"{base}/web/shop.html")
    snap = await tools.take_snapshot(page, session)
    products = next(x for x in snap["links"] if x["text"] == "Products")
    assert (await ex.run(act("click", element_id=products["id"]), session, browser)).startswith("ok: clicked 'Products'")


# ================================================================ the model never sees saved values (rule 1)
import json  # noqa: E402
from app.tools import hide_profile_text, hide_profile_values  # noqa: E402


def test_hide_profile_text_replaces_whole_words_only():
    p = DEMO_PROFILE
    assert hide_profile_text("Welcome Ramesh Kumar!", p) == "Welcome [saved full_name]!"
    assert hide_profile_text("welcome RAMESH   kumar", p) == "welcome [saved full_name]"
    assert hide_profile_text("mail ramesh@example.com now", p) == "mail [saved email] now"
    assert hide_profile_text("lives at 12  MG Road", p) == "lives at [saved address]"   # spacing does not matter
    assert hide_profile_text("pin 560001 and 5600012", p) == "pin [saved pin_code] and 5600012"   # 6 digits: whole number only
    assert hide_profile_text("call 98765 43210", p) == "call [saved phone]"
    assert hide_profile_text("call 9876-543-210", p) == "call [saved phone]"
    # short values ("male", "75") are left alone in running text; a saved value of 6+ characters is hidden even
    # when the page uses the same word ("General"), the price of an absolute rule
    assert hide_profile_text("She is female and 75% disabled in General", p) ==         "She is female and 75% disabled in [saved category]"
    assert hide_profile_text("id 0000 1111 2222", p) == "id [hidden]"                # sensitive: always scrubbed
    assert hide_profile_text("nothing here", {}) == "nothing here"


def test_hide_profile_values_hides_what_the_agent_typed_whatever_the_page_shows():
    session = Session(profile=copy.deepcopy(DEMO_PROFILE))
    snap = {"page_title": "Hello Ramesh Kumar", "summary": "Form for Ramesh Kumar, born 1980-03-04.",
            "headings": ["Apply"], "errors": [], "links": [{"id": "l1", "text": "Help"}], "tabs": [], "buttons": [],
            "fields": [{"id": "f1", "label": "Full name", "value": "Ramesh Kumar"},
                       {"id": "f2", "label": "Date of birth", "value": "04/03/1980"},          # reformatted by the page
                       {"id": "f3", "label": "Disability %", "value": "75"},                      # short value: exact match
                       {"id": "f4", "label": "Notes", "value": "75 years of service"},         # not a whole match: left alone
                       {"id": "f5", "label": "Search", "value": "kalpana chawla"}]}
    session.expected = {"f2": {"source": "profile:dob"}}
    before = copy.deepcopy(snap)
    out = hide_profile_values(snap, session)
    assert snap == before                                                    # the original is untouched
    assert out["page_title"] == "Hello [saved full_name]"
    assert out["summary"] == "Form for [saved full_name], born [saved dob]."
    assert [f["value"] for f in out["fields"]] == [
        "[saved full_name]", "[saved dob]", "[saved disability_percent]", "75 years of service", "kalpana chawla"]
    assert "Ramesh" not in json.dumps(out) and "1980" not in json.dumps(out)


async def test_results_and_page_text_hide_saved_values(setup, monkeypatch):
    ex, session, browser, page = setup(PORTAL_URL)
    session.elements["l1"]["label"] = "Welcome Ramesh Kumar"
    session.locators["l1"] = "#l1"
    result = await ex.run(act("click", element_id="l1"), session, browser)
    assert result == "ok: clicked 'Welcome [saved full_name]'"

    async def main_text(p, max_chars=4000):
        return "Thank you Ramesh Kumar. Your reference is 42. We will call 9876543210."
    monkeypatch.setattr(perception, "main_text", main_text)
    text = await ex.run(act("read_page", mode="main_text"), session, browser)
    assert "Ramesh" not in text and "9876543210" not in text and "[saved phone]" in text



# ================================================================ the total shown on the page is kept with the held action
from app.tools import find_total  # noqa: E402


@pytest.mark.parametrize("text,expected", [
    ("Your cart\nTotal: 249 rupees\nPlace order", "249 rupees"),
    ("Total \u20b91,249.50", "\u20b91,249.50"),
    ("Grand total: Rs. 500", "Rs. 500"),
    ("TOTAL INR 75", "INR 75"),
    ("Subtotal 100 rupees\nTotal 118 rupees", "118 rupees"),          # the last total wins, "Subtotal" is not a total
    ("Total items: 3", None),                                         # a count is not money
    ("Total: 3", None),
    ("Subtotal 100 rupees", None),
    ("Free delivery", None),
    ("", None),
])
async def test_find_total_reads_only_real_amounts(monkeypatch, text, expected):
    async def main_text(page, max_chars=4000):
        return text
    monkeypatch.setattr(perception, "main_text", main_text)
    assert await find_total(object()) == expected


async def test_find_total_survives_a_page_that_cannot_be_read(monkeypatch):
    async def broken(page, max_chars=4000):
        raise RuntimeError("navigating")
    monkeypatch.setattr(perception, "main_text", broken)
    assert await find_total(object()) is None


async def test_a_held_action_carries_the_total_when_the_page_shows_one(setup, monkeypatch):
    ex, session, browser, page = setup(PORTAL_URL)

    async def main_text(p, max_chars=4000):
        return "Cart\nTotal: 249 rupees"
    monkeypatch.setattr(perception, "main_text", main_text)
    await ex.run(act("click", element_id="b1"), session, browser)
    assert session.pending_action["total_text"] == "249 rupees"


async def test_a_held_action_without_a_total_has_no_total_key(setup, monkeypatch):
    ex, session, browser, page = setup(PORTAL_URL)

    async def main_text(p, max_chars=4000):
        return "Please review your details"
    monkeypatch.setattr(perception, "main_text", main_text)
    await ex.run(act("click", element_id="b1"), session, browser)
    assert "total_text" not in session.pending_action
