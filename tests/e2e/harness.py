"""Shared end-to-end harness for JEV-07.

The harness is deliberately honest about the state of the code. Any function or method
that still has a ``# STUB:`` marker is reported as a blocker, and dependent tests skip
with that reason. Nothing here treats stub behaviour as a passing demo run.

What lives here:
- an in-process FastAPI server on a random port (uvicorn) with a health wait and clean stop
- an async WebSocket client for ``/ws/console`` with event waits and a redacted event dump
- a scripted fake ``app.llm.llm`` with queued tool calls
- a static fixture server for the self-contained pages in ``tests/e2e/fixtures``
- deterministic fictional profile and session helpers for the safety checks
- assertions for raw sensitive values, irreversible controls, and read-back masking
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import functools
import importlib
import inspect
import json
import os
import re
import socket
import tempfile
import threading
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import uvicorn
import websockets

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Fictional values, copied from the CORE-01 profile stub so typed runs are deterministic.
PROFILE: dict[str, str] = {
    "full_name": "Ramesh Kumar",
    "dob": "1980-03-04",
    "gender": "male",
    "address": "12 MG Road",
    "city": "Bengaluru",
    "state": "Karnataka",
    "pin_code": "560001",
    "phone": "9876543210",
    "email": "ramesh@example.com",
    "annual_income": "120000",
    "category": "General",
    "disability_percent": "75",
    "aadhaar": "000011112222",
    "bank_account": "000000001234",
    "ifsc": "TEST0000001",
}
SENSITIVE_VALUES: dict[str, str] = {
    "aadhaar": PROFILE["aadhaar"],
    "bank_account": PROFILE["bank_account"],
    "ifsc": PROFILE["ifsc"],
}
CONFIRM_INSTRUCTION = "Say confirm to go ahead, or say change followed by the field name."

# Every Console wait is capped here. A real backend step takes a few seconds; the old
# 60-90s waits only made a failure slow. 30s still leaves room for a cold browser start.
E2E_WAIT = 30.0


# --------------------------------------------------------------------------------------
# Stub detection and blockers
# --------------------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class StubSpec:
    key: str
    module: str
    attr: str | None
    ticket: str
    module_fallback: bool = False


_STUB_SPECS: tuple[StubSpec, ...] = (
    StubSpec("agent.handle_utterance", "app.agent", "handle_utterance", "CORE-10/11"),
    StubSpec("agent.run_task", "app.agent", "run_task", "CORE-10"),
    StubSpec("tools.ToolExecutor.run", "app.tools", "ToolExecutor.run", "CORE-08"),
    StubSpec("tools.commit_pending", "app.tools", "commit_pending", "CORE-12"),
    StubSpec("browser.BrowserController.start", "app.browser", "BrowserController.start",
             "BRW-02"),
    StubSpec("browser.BrowserController.goto", "app.browser", "BrowserController.goto",
             "BRW-02"),
    StubSpec("perception.snapshot", "app.perception", "snapshot", "BRW-03"),
    StubSpec("perception.main_text", "app.perception", "main_text", "BRW-03"),
    StubSpec("humancheck.challenge_present", "app.humancheck", "challenge_present", "BRW-04"),
    StubSpec("gate.check", "app.gate", "check", "JEV-04/05"),
    StubSpec("verifier.verify", "app.verifier", "verify", "JEV-02"),
    StubSpec("readback.build_readback", "app.readback", "build_readback", "JEV-03"),
    StubSpec("readback.describe_pending", "app.readback", "describe_pending", "JEV-03",
             module_fallback=True),
    StubSpec("audit.log_event", "app.audit", "log_event", "JEV-06"),
    StubSpec("profile.load_profile", "app.profile", "load_profile", "CORE-07"),
)
STUB_BY_KEY = {spec.key: spec for spec in _STUB_SPECS}


def source_contains_stub(obj: Any) -> bool:
    """True when inspect.getsource(obj) contains a STUB: marker."""
    try:
        source = inspect.getsource(obj)
    except (OSError, TypeError):
        return False
    return "STUB:" in source


def _resolve_attr(module_name: str, attr_path: str) -> Any:
    obj: Any = importlib.import_module(module_name)
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    return obj


def is_stub(key: str) -> bool:
    """True when the named contract member is still a stub."""
    spec = STUB_BY_KEY[key]
    if spec.attr is not None and source_contains_stub(_resolve_attr(spec.module, spec.attr)):
        return True
    if spec.module_fallback:
        return source_contains_stub(importlib.import_module(spec.module))
    return False


def blockers(keys: Sequence[str]) -> list[StubSpec]:
    return [STUB_BY_KEY[key] for key in keys if is_stub(key)]


_DEMO_KEYS: dict[str, tuple[str, ...]] = {
    "A": (
        "agent.handle_utterance",
        "agent.run_task",
        "tools.ToolExecutor.run",
        "browser.BrowserController.start",
        "browser.BrowserController.goto",
        "perception.snapshot",
        "perception.main_text",
    ),
    "B": (
        "agent.handle_utterance",
        "agent.run_task",
        "tools.ToolExecutor.run",
        "tools.commit_pending",
        "browser.BrowserController.start",
        "browser.BrowserController.goto",
        "perception.snapshot",
        "perception.main_text",
        "humancheck.challenge_present",
        "gate.check",
        "verifier.verify",
        "readback.build_readback",
        "readback.describe_pending",
    ),
    "C": (
        "agent.handle_utterance",
        "agent.run_task",
        "tools.ToolExecutor.run",
        "tools.commit_pending",
        "browser.BrowserController.start",
        "browser.BrowserController.goto",
        "perception.snapshot",
        "perception.main_text",
        "humancheck.challenge_present",
        "gate.check",
        "readback.build_readback",
        "readback.describe_pending",
    ),
}
_CORE_KEYS = frozenset({"agent.handle_utterance", "agent.run_task", "tools.ToolExecutor.run"})


class BlockedScenario(RuntimeError):
    """Raised when a scenario cannot run yet because a contract member is still a stub."""


def _describe(blockers_found: Sequence[StubSpec]) -> str:
    return ", ".join(f"{spec.key} ({spec.ticket})" for spec in blockers_found)


def scenario_blockers(scenario: str) -> list[StubSpec]:
    return blockers(_DEMO_KEYS[scenario.upper()])


def scenario_skip_reason(scenario: str) -> str | None:
    """A clear skip reason, or None when the scenario can run."""
    found = scenario_blockers(scenario)
    if found:
        if any(spec.key in _CORE_KEYS for spec in found):
            return (f"blocked until CORE-11: {_describe(found)} still contain a 'STUB:' marker")
        return (f"blocked by e2e dependencies: {_describe(found)} still contain a "
                "'STUB:' marker")
    if scenario.upper() == "B":
        blocker = core12_blocker()
        if blocker:
            return (f"blocked until CORE-12 (verify/readback/confirm state machine): "
                    f"{blocker}")
    return None


def core12_blocker() -> str | None:
    """Report the CORE-12 gap in the verify/read-back/confirm state machine, else None.

    CORE-12 replaces the placeholder confirmation with the form check, read-back and
    confirm state machine. Until it lands, demo B cannot pass, so the test must skip
    with this exact reason instead of treating the partial flow as a pass.
    """
    if is_stub("tools.commit_pending"):
        return "tools.commit_pending (CORE-12) still contains a 'STUB:' marker"
    agent = importlib.import_module("app.agent")
    try:
        source = inspect.getsource(agent.begin_confirmation)
    except (OSError, TypeError) as exc:
        return f"app.agent.begin_confirmation cannot be inspected ({type(exc).__name__})"
    if "CORE-12" in source:
        return "agent.begin_confirmation still says CORE-12 adds the form check"
    return None


def stub_skip_reason(*keys: str) -> str | None:
    found = [STUB_BY_KEY[key] for key in keys if is_stub(key)]
    if not found:
        return None
    return f"not testable yet: {_describe(found)} still contain a 'STUB:' marker"


def require_ready(scenario: str) -> None:
    reason = scenario_skip_reason(scenario)
    if reason:
        raise BlockedScenario(reason)


# --------------------------------------------------------------------------------------
# Sensitive-value masking and assertions
# --------------------------------------------------------------------------------------

def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value))


def digits(value: Any) -> str:
    """Digits only, useful for checking spaced spoken numbers."""
    return _digits(value)


def _grouped(value: str, size: int = 4) -> str:
    return " ".join(value[i:i + size] for i in range(0, len(value), size))


def _hyphenated(value: str, size: int = 4) -> str:
    return "-".join(value[i:i + size] for i in range(0, len(value), size))


def mask_value(value: Any) -> str:
    text = str(value)
    if len(text) <= 4:
        return "*" * len(text)
    return ("*" * (len(text) - 4)) + text[-4:]


def redact(text: str) -> str:
    """Mask the fictional sensitive values before any event or error is printed."""
    for value in SENSITIVE_VALUES.values():
        if not value:
            continue
        variants = {
            value,
            _grouped(value),
            _grouped(value, 3),
            _hyphenated(value),
            " ".join(value),
        }
        for variant in variants:
            text = text.replace(variant, mask_value(value))
    return text


def assert_no_sensitive_text(text: str, context: str) -> None:
    """Fail if a raw aadhaar, bank account or IFSC value appears in text."""
    lowered = text.casefold()
    digits = _digits(text)
    for key, value in SENSITIVE_VALUES.items():
        variants = {
            value.casefold(),
            _grouped(value).casefold(),
            _grouped(value, 3).casefold(),
            _hyphenated(value).casefold(),
            " ".join(value).casefold(),
        }
        if any(variant and variant in lowered for variant in variants):
            raise AssertionError(
                f"raw {key} appeared in {context}; hard rule 4 forbids it"
            )
        if key in {"aadhaar", "bank_account"}:
            value_digits = _digits(value)
            if value_digits and value_digits in digits:
                raise AssertionError(
                    f"raw {key} appeared in {context}; hard rule 4 forbids it"
                )


# --------------------------------------------------------------------------------------
# Fixture site
# --------------------------------------------------------------------------------------

class _FixtureHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: Any) -> None:
        super().__init__(address, handler)
        self._lock = threading.Lock()
        self._human_done = False
        self._portal_attempts = 0
        self._portal_submissions = 0
        self._shop_orders = 0

    def mark_human_done(self) -> None:
        with self._lock:
            self._human_done = True

    def reset_human(self) -> None:
        with self._lock:
            self._human_done = False

    def record_portal_submit(self) -> None:
        with self._lock:
            self._portal_submissions += 1

    def record_portal_attempt(self) -> None:
        with self._lock:
            self._portal_attempts += 1

    def record_shop_order(self) -> None:
        with self._lock:
            self._shop_orders += 1

    def state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "human_done": self._human_done,
                "portal_attempts": self._portal_attempts,
                "portal_submissions": self._portal_submissions,
                "shop_orders": self._shop_orders,
            }


class _FixtureHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        server: _FixtureHTTPServer = self.server  # type: ignore[assignment]
        if path == "/__human_state":
            self._json({"done": server.state()["human_done"]})
            return
        if path == "/__human_done":
            server.mark_human_done()
            self._json({"done": True})
            return
        if path == "/__state":
            self._json(server.state())
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        server: _FixtureHTTPServer = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length:
            self.rfile.read(length)
        if path == "/__portal_attempt":
            server.record_portal_attempt()
            self._json({"ok": True})
            return
        if path == "/__portal_submit":
            server.record_portal_submit()
            self._json({"ok": True})
            return
        if path == "/__shop_order":
            server.record_shop_order()
            self._json({"ok": True})
            return
        self._json({"error": "not found"}, status=404)


@dataclasses.dataclass
class FixtureSite:
    base_url: str
    server: _FixtureHTTPServer

    def url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @property
    def portal_submissions(self) -> int:
        return int(self.server.state()["portal_submissions"])

    @property
    def portal_attempts(self) -> int:
        return int(self.server.state()["portal_attempts"])

    @property
    def shop_orders(self) -> int:
        return int(self.server.state()["shop_orders"])

    def mark_human_done(self) -> None:
        self.server.mark_human_done()

    def reset_human(self) -> None:
        self.server.reset_human()

    async def wait_for_portal_submission(self, timeout: float = 15.0) -> int:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if self.portal_submissions:
                return self.portal_submissions
            await asyncio.sleep(0.05)
        raise AssertionError(
            f"portal form was not submitted within {timeout:.0f}s "
            f"(server state: {self.server.state()})"
        )

    async def wait_for_shop_order(self, timeout: float = 15.0) -> int:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if self.shop_orders:
                return self.shop_orders
            await asyncio.sleep(0.05)
        raise AssertionError(
            f"shop order was not placed within {timeout:.0f}s "
            f"(server state: {self.server.state()})"
        )


@contextlib.contextmanager
def fixture_site() -> Iterator[FixtureSite]:
    """Serve tests/e2e/fixtures on a random localhost port."""
    handler = functools.partial(_FixtureHandler, directory=str(FIXTURES))
    server = _FixtureHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, name="e2e-fixtures", daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield FixtureSite(base_url=base_url, server=server)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# --------------------------------------------------------------------------------------
# Config patching for typed runs
# --------------------------------------------------------------------------------------

@contextlib.contextmanager
def _patch_attr(module: Any, attr: str, value: Any) -> Iterator[None]:
    if not hasattr(module, attr):
        yield
        return
    original = getattr(module, attr)
    setattr(module, attr, value)
    try:
        yield
    finally:
        setattr(module, attr, original)


@contextlib.contextmanager
def fixture_config(site: FixtureSite) -> Iterator[Path]:
    """Point SEARCH_URL and SITES_PATH at the fixture pages for the duration of a run."""
    from app import config as app_config

    sites = [
        {"id": "e2e_search", "aliases": ["mock search", "search"],
         "url": site.url("search.html"), "domain": "127.0.0.1", "trusted": True},
        {"id": "e2e_article", "aliases": ["article"],
         "url": site.url("article.html"), "domain": "127.0.0.1", "trusted": True},
        {"id": "e2e_portal", "aliases": ["demo portal", "pension portal"],
         "url": site.url("portal.html"), "domain": "127.0.0.1", "trusted": True},
        {"id": "e2e_shop", "aliases": ["demo shop", "shop"],
         "url": site.url("shop.html"), "domain": "127.0.0.1", "trusted": True},
        {"id": "e2e_inbox", "aliases": ["my mail", "mock inbox"],
         "url": site.url("inbox.html"), "domain": "127.0.0.1", "trusted": False},
    ]
    search_url = site.url("search.html") + "?q={q}"
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        try:
            json.dump(sites, tmp)
        finally:
            tmp.close()
        sites_path = Path(tmp.name)
        old_env = os.environ.get("SEARCH_URL")
        os.environ["SEARCH_URL"] = search_url
        with contextlib.ExitStack() as stack:
            stack.enter_context(_patch_attr(app_config, "SITES_PATH", sites_path))
            stack.enter_context(_patch_attr(app_config, "SEARCH_URL", search_url))
            for module_name in ("app.tools", "app.agent"):
                module = importlib.import_module(module_name)
                stack.enter_context(_patch_attr(module, "SEARCH_URL", search_url))
                stack.enter_context(_patch_attr(module, "SITES_PATH", sites_path))
            try:
                yield sites_path
            finally:
                if old_env is None:
                    os.environ.pop("SEARCH_URL", None)
                else:
                    os.environ["SEARCH_URL"] = old_env
    finally:
        with contextlib.suppress(OSError):
            Path(tmp.name).unlink()


# --------------------------------------------------------------------------------------
# Fake profile and scripted LLM
# --------------------------------------------------------------------------------------

@contextlib.contextmanager
def _patch_callable(module: Any, attr: str, value: Callable[..., Any]) -> Iterator[None]:
    if not callable(getattr(module, attr, None)):
        yield
        return
    original = getattr(module, attr)
    setattr(module, attr, value)
    try:
        yield
    finally:
        setattr(module, attr, original)


@contextlib.contextmanager
def _patch_aliases(module: Any, original: Callable[..., Any],
                   replacement: Callable[..., Any]) -> Iterator[None]:
    """Patch every module attribute that still points at the original function."""
    with contextlib.ExitStack() as stack:
        for attr, value in list(vars(module).items()):
            if value is original:
                stack.enter_context(_patch_attr(module, attr, replacement))
        yield


@contextlib.contextmanager
def deterministic_config() -> Iterator[None]:
    """Force the settings that make an e2e run repeatable.

    - ``BROWSER_HEADLESS=True`` keeps Playwright's Chromium off the desktop.
    - ``GATE_BACKEND="rules"`` means no live Jev call can change a decision mid-run.

    The app reads both from ``app.config`` at call time, so patching the module is enough
    even when ``app.main`` or ``app.agent`` was imported earlier.
    """
    from app import config as app_config

    with contextlib.ExitStack() as stack:
        stack.enter_context(_patch_attr(app_config, "BROWSER_HEADLESS", True))
        stack.enter_context(_patch_attr(app_config, "GATE_BACKEND", "rules"))
        yield


@contextlib.contextmanager
def fake_profile(profile: dict[str, str] | None = None) -> Iterator[None]:
    """Return the fictional profile for any PIN, without touching the real profile file."""
    values = dict(profile or PROFILE)

    def load_profile(pin: str) -> dict[str, str]:
        return dict(values)

    def profile_exists() -> bool:
        return True

    with contextlib.ExitStack() as stack:
        profile_module = importlib.import_module("app.profile")
        original_load = profile_module.load_profile
        original_exists = profile_module.profile_exists
        stack.enter_context(_patch_callable(profile_module, "load_profile", load_profile))
        stack.enter_context(_patch_callable(profile_module, "profile_exists", profile_exists))
        for module_name in ("app.agent", "app.main"):
            module = importlib.import_module(module_name)
            stack.enter_context(_patch_aliases(module, original_load, load_profile))
            stack.enter_context(_patch_aliases(module, original_exists, profile_exists))
        yield


def seed_session_profile(profile: dict[str, str] | None = None) -> None:
    """Put the fictional profile in the live hub, as onboarding does after the PIN.

    UI-07 (the unlock step) is not part of these runs, so the harness seeds the session
    directly. That is scripted setup, not a shortcut in the agent: every fill still goes
    through the real executor and placeholder substitution.
    """
    from app.main import app as fastapi_app

    hub = getattr(fastapi_app.state, "hub", None)
    if hub is None:
        raise RuntimeError("the app server has no hub yet; connect the Console first")
    hub.ctx.session.profile = dict(profile or PROFILE)


def tool(name: str, **args: Any) -> dict[str, Any]:
    return {"tool_call": {"name": name, "args": args}}


def reply(text: str) -> dict[str, Any]:
    return {"text": text, "tool_call": None}


def _flatten_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ("content", "text", "result", "summary", "label", "name"):
            item = value.get(key)
            if isinstance(item, str):
                parts.append(item)
        for item in value.values():
            if isinstance(item, (dict, list, tuple)):
                parts.extend(_flatten_text(item))
        return parts
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            parts.extend(_flatten_text(item))
        return parts
    return []


def _walk_dicts(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk_dicts(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_dicts(item)


class StepContext:
    """Everything a scripted step may inspect."""

    def __init__(self, messages: Sequence[dict[str, Any]], tools: Sequence[dict] | None,
                 index: int) -> None:
        self.messages = list(messages)
        self.tools = tools
        self.index = index

    def _texts(self) -> Iterator[str]:
        for message in reversed(self.messages):
            for text in _flatten_text(message):
                yield text

    def _candidates(self, label: str) -> list[tuple[str, str]]:
        needle = label.casefold()
        found: list[tuple[str, str]] = []
        for text in self._texts():
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError):
                parsed = None
            if parsed is not None:
                for obj in _walk_dicts(parsed):
                    element_id = obj.get("id")
                    label_text = obj.get("label") or obj.get("text") or obj.get("name")
                    if isinstance(element_id, str) and isinstance(label_text, str):
                        if needle in label_text.casefold():
                            found.append((element_id, label_text))
            for match in re.finditer(r"\{[^{}]*\"id\"\s*:\s*\"([^\"]+)\"[^{}]*\}", text):
                block = match.group(0)
                label_match = re.search(r"\"(?:label|text|name)\"\s*:\s*\"([^\"]*)\"", block)
                if label_match and needle in label_match.group(1).casefold():
                    found.append((match.group(1), label_match.group(1)))
        return found

    def element_id(self, label: str, fallback: str | None = None) -> str | None:
        candidates = self._candidates(label)
        if candidates:
            return candidates[0][0]
        return fallback

    def field_id(self, label: str, fallback: str | None = None) -> str | None:
        return self.element_id(label, fallback)

    def button_id(self, label: str, fallback: str | None = None) -> str | None:
        return self.element_id(label, fallback)

    def link_id(self, label: str, fallback: str | None = None) -> str | None:
        return self.element_id(label, fallback)


@dataclasses.dataclass
class LLMCall:
    index: int
    step: Any
    tools: Sequence[dict] | None
    messages: Sequence[dict[str, Any]]


class FakeLLM:
    """Queued tool calls behind the real ``app.llm.llm`` signature.

    A script entry is one of:
    - a dict from ``tool(...)`` or ``reply(...)``
    - a callable taking a :class:`StepContext` and returning the same
    - a plain string, returned as text

    Calls without tools are treated as planning or answer calls and do not consume the
    queue. When the queue runs out, a plain text reply is returned; an agent should end
    the task on it instead of inventing a new action.
    """

    def __init__(self, script: Sequence[Any]) -> None:
        self._queue = list(script)
        self._lock = asyncio.Lock()
        self.calls: list[LLMCall] = []

    @property
    def remaining(self) -> int:
        return len(self._queue)

    async def __call__(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        async with self._lock:
            index = len(self.calls)
            step = None
            if tools:
                step = self._queue.pop(0) if self._queue else None
            self.calls.append(LLMCall(index=index, step=step, tools=tools, messages=list(messages)))
        if not tools:
            return {"text": "I will work through the task one step at a time.",
                    "tool_call": None}
        if step is None:
            return {"text": "Scripted run complete.", "tool_call": None}
        if callable(step):
            step = step(StepContext(messages, tools, index))
            if inspect.isawaitable(step):
                step = await step
            self.calls[index].step = step
        if step is None:
            return {"text": "Scripted run complete.", "tool_call": None}
        if isinstance(step, str):
            return {"text": step, "tool_call": None}
        if "tool_call" in step:
            return {"text": step.get("text"), "tool_call": step.get("tool_call")}
        if "name" in step:
            return {"text": None,
                    "tool_call": {"name": step["name"], "args": step.get("args", {})}}
        return {"text": str(step.get("text", "")), "tool_call": None}

    def summary(self, limit: int = 30) -> str:
        lines: list[str] = []
        for call in self.calls[-limit:]:
            step = call.step
            if isinstance(step, dict) and isinstance(step.get("tool_call"), dict):
                call_data = step["tool_call"]
                name = call_data.get("name")
                args = json.dumps(call_data.get("args", {}), ensure_ascii=False)
                lines.append(f"#{call.index} {name}({redact(args)})")
            elif isinstance(step, str):
                lines.append(f"#{call.index} text: {redact(step[:120])}")
            elif step is None:
                lines.append(f"#{call.index} (queue empty, plain text)")
            else:
                lines.append(f"#{call.index} (dynamic step)")
        return "\n".join(lines) if lines else "(no LLM calls)"

    def assert_no_sensitive_prompts(self) -> None:
        """Hard rule 1 and 4: the model and tool results never carry raw values."""
        for call in self.calls:
            payload = json.dumps(list(call.messages), ensure_ascii=False, default=str)
            assert_no_sensitive_text(payload, f"LLM prompt (call {call.index})")


@contextlib.contextmanager
def fake_llm(script: Sequence[Any]) -> Iterator[FakeLLM]:
    """Replace app.llm.llm (and any imported copy) for one run."""
    fake = FakeLLM(script)
    with contextlib.ExitStack() as stack:
        llm_module = importlib.import_module("app.llm")
        original = llm_module.llm
        stack.enter_context(_patch_callable(llm_module, "llm", fake))
        for module_name in ("app.agent", "app.main"):
            module = importlib.import_module(module_name)
            stack.enter_context(_patch_aliases(module, original, fake))
        yield fake


# --------------------------------------------------------------------------------------
# In-process FastAPI server and WebSocket client
# --------------------------------------------------------------------------------------

def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclasses.dataclass(frozen=True)
class AppServer:
    base_url: str
    ws_url: str


@contextlib.asynccontextmanager
async def app_server() -> AsyncIterator[AppServer]:
    """Start uvicorn in this process on a free port, wait for /health, stop cleanly."""
    with deterministic_config():
        from app.main import app as fastapi_app

        # app.main keeps one Hub on the FastAPI app for the process lifetime. A new
        # server must start from a fresh Context, otherwise a CLI run of A then C sees
        # A's DONE state. The previous app_server has already shut its Hub down.
        fastapi_app.state.hub = None

        port = free_port()
        config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="warning",
                                lifespan="on")
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        task = asyncio.create_task(server.serve(), name="e2e-uvicorn")
        base_url = f"http://127.0.0.1:{port}"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 20
        last_error: Exception | None = None
        try:
            async with httpx.AsyncClient(timeout=1.0) as http:
                while True:
                    if task.done():
                        error = task.exception()
                        raise RuntimeError(f"uvicorn stopped before /health: {error!r}")
                    try:
                        response = await http.get(f"{base_url}/health")
                        if response.status_code == 200 and response.json().get("status") == "ok":
                            break
                    except Exception as exc:  # noqa: BLE001 - startup race
                        last_error = exc
                    if loop.time() > deadline:
                        raise RuntimeError(
                            f"timed out waiting for {base_url}/health; last error: {last_error!r}"
                        )
                    await asyncio.sleep(0.05)
            yield AppServer(base_url=base_url, ws_url=f"ws://127.0.0.1:{port}/ws/console")
        finally:
            server.should_exit = True
            try:
                await asyncio.wait_for(task, timeout=10)
            except asyncio.TimeoutError:
                server.force_exit = True
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            except asyncio.CancelledError:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            except Exception:  # noqa: BLE001 - shutdown noise must not hide the test result
                pass


@dataclasses.dataclass(frozen=True)
class Event:
    seq: int
    direction: str
    data: dict[str, Any]

    @property
    def type(self) -> str:
        return str(self.data.get("type", ""))

    @property
    def text(self) -> str:
        return str(self.data.get("text", ""))


class ConsoleClient:
    """Async WebSocket client for /ws/console with typed waits and a safe dump."""

    def __init__(self, websocket: Any) -> None:
        self._ws = websocket
        self.events: list[Event] = []
        self._claimed: set[int] = set()
        self._condition = asyncio.Condition()
        self._closed = False
        self._error: BaseException | None = None
        self._task = asyncio.create_task(self._recv_loop(), name="e2e-console-recv")

    async def _append(self, direction: str, data: dict[str, Any]) -> Event:
        async with self._condition:
            event = Event(seq=len(self.events) + 1, direction=direction, data=data)
            self.events.append(event)
            self._condition.notify_all()
        return event

    async def _recv_loop(self) -> None:
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", "replace")
                try:
                    data = json.loads(raw)
                except (TypeError, ValueError):
                    data = {"type": "raw", "raw": raw}
                if not isinstance(data, dict):
                    data = {"type": "raw", "raw": data}
                await self._append("in", data)
        except asyncio.CancelledError:
            raise
        except websockets.exceptions.ConnectionClosed as exc:
            self._error = exc
        except Exception as exc:  # noqa: BLE001 - recorded for diagnostics
            self._error = exc
        finally:
            self._closed = True
            async with self._condition:
                self._condition.notify_all()

    async def _send(self, data: dict[str, Any]) -> Event:
        event = await self._append("out", data)
        await self._ws.send(json.dumps(data))
        return event

    async def send_utterance(self, text: str) -> Event:
        return await self._send({"type": "utterance", "text": text})

    async def send_key(self, name: str) -> Event:
        return await self._send({"type": "key", "name": name})

    async def wait_for(self, predicate: Callable[[Event], bool], description: str,
                       timeout: float = E2E_WAIT) -> Event:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            async with self._condition:
                for event in self.events:
                    if event.seq not in self._claimed and predicate(event):
                        self._claimed.add(event.seq)
                        return event
                remaining = deadline - loop.time()
                if remaining <= 0 or self._closed:
                    break
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
        error = f"\nreceiver error: {self._error!r}" if self._error else ""
        raise AssertionError(
            f"timed out after {timeout:.1f}s waiting for {description}{error}\n\n{self.dump()}"
        )

    async def wait_for_state(self, name: str, timeout: float = E2E_WAIT) -> Event:
        return await self.wait_for(
            lambda event: event.direction == "in" and event.type == "state"
            and event.data.get("name") == name,
            f"state {name}", timeout,
        )

    async def expect_event(self, event_type: str,
                           predicate: Callable[[Event], bool] | None = None,
                           timeout: float = E2E_WAIT) -> Event:
        """Wait for the next inbound event of ``event_type`` that matches predicate."""
        def matches(event: Event) -> bool:
            if event.direction != "in" or event.type != event_type:
                return False
            return predicate is None or predicate(event)

        return await self.wait_for(matches, f"{event_type} event", timeout)

    async def wait_for_speak(self, substring: str | None = None,
                             timeout: float = E2E_WAIT) -> Event:
        needle = substring.casefold() if substring else None

        def matches(event: Event) -> bool:
            if event.direction != "in" or event.type != "speak":
                return False
            return needle is None or needle in str(event.data.get("text", "")).casefold()

        description = f"speak containing {substring!r}" if substring else "speak event"
        return await self.wait_for(matches, description, timeout)

    async def wait_for_pending(self, timeout: float = E2E_WAIT) -> Event:
        return await self.wait_for(
            lambda event: event.direction == "in" and event.type == "pending",
            "pending event", timeout,
        )

    async def wait_for_human_check(self, timeout: float = E2E_WAIT) -> Event:
        keywords = (
            "robot", "human check", "captcha", "say done",
            "when you are done", "complete the check", "payment", "hand over",
            "hand-off", "handoff", "card",
        )

        def matches(event: Event) -> bool:
            if event.direction != "in":
                return False
            if event.type == "state" and event.data.get("name") == "NEEDS_HUMAN_CHECK":
                return True
            if event.type == "speak":
                text = str(event.data.get("text", "")).casefold()
                return any(keyword in text for keyword in keywords)
            return False

        return await self.wait_for(matches, "human-check pause or hand-off", timeout)

    async def wait_for_payment_handoff(self, timeout: float = E2E_WAIT,
                                       after_seq: int = 0) -> Event:
        keywords = ("payment", "hand over", "hand-off", "handoff", "card", "human")

        def matches(event: Event) -> bool:
            if event.direction != "in" or event.seq <= after_seq:
                return False
            if event.type == "state" and event.data.get("name") == "NEEDS_HUMAN_CHECK":
                return True
            if event.type == "speak":
                text = str(event.data.get("text", "")).casefold()
                return any(keyword in text for keyword in keywords)
            return False

        return await self.wait_for(matches, "payment hand-off", timeout)

    async def wait_for_ack(self, timeout: float = E2E_WAIT, after_seq: int = 0) -> Event:
        def matches(event: Event) -> bool:
            if event.direction != "in" or event.type != "speak" or event.seq <= after_seq:
                return False
            text = str(event.data.get("text", ""))
            compact = re.sub(r"[^A-Za-z0-9]", "", text).upper()
            return "ACKNOWLEDG" in compact or "ACK20260042" in compact

        return await self.wait_for(matches, "acknowledgment", timeout)

    def events_of_type(self, event_type: str, direction: str = "in") -> list[Event]:
        return [event for event in self.events
                if event.direction == direction and event.type == event_type]

    def speaks(self) -> list[Event]:
        return self.events_of_type("speak")

    def speaks_until(self, seq: int) -> list[Event]:
        return [event for event in self.speaks() if event.seq <= seq]

    def all_text(self) -> str:
        return "\n".join(json.dumps(event.data, ensure_ascii=False) for event in self.events)

    def assert_no_sensitive_events(self) -> None:
        assert_no_sensitive_text(self.all_text(), "Console events")

    def _confirm_seq(self, after_seq: int) -> int | None:
        for event in self.events:
            if event.direction != "out" or event.seq <= after_seq:
                continue
            if event.type != "utterance":
                continue
            text = str(event.data.get("text", "")).strip().casefold().rstrip(".!?")
            if text in {"confirm", "yes", "yes confirm", "confirm it", "ok", "okay"}:
                return event.seq
            if text.startswith("confirm") or text.startswith("yes"):
                return event.seq
        return None

    def assert_no_irreversible_before_confirm(self, labels: Sequence[str]) -> None:
        """Prove that no held irreversible control ran before the user said confirm."""
        pending_events = self.events_of_type("pending")
        if not pending_events:
            raise AssertionError(f"no pending event was emitted\n\n{self.dump()}")
        pending = pending_events[0]
        confirm_seq = self._confirm_seq(pending.seq)
        if confirm_seq is None:
            raise AssertionError(
                f"no 'confirm' utterance was sent after the pending action\n\n{self.dump()}"
            )
        lowered_labels = [label.casefold() for label in labels]
        success_words = (
            "order placed", "submitted successfully", "application submitted",
            "payment complete", "purchased", "thank you for your application",
        )
        for event in self.events:
            if event.seq >= confirm_seq:
                continue
            if event.direction != "in":
                continue
            if event.type == "step":
                action = str(event.data.get("action", "")).casefold()
                blob = json.dumps(event.data, ensure_ascii=False).casefold()
                if any(word in action for word in ("click", "press", "submit", "commit")) \
                        and any(label in blob for label in lowered_labels):
                    result = str(event.data.get("result", "")).casefold()
                    held = any(word in result for word in
                               ("held", "pending", "await", "confirm", "not clicked",
                                "waiting", "without"))
                    if not held:
                        raise AssertionError(
                            f"irreversible control ran before confirm: {event.data}\n\n"
                            f"{self.dump()}"
                        )
            if event.type in {"speak", "alert"}:
                text = str(event.data.get("text") or event.data.get("message") or "").casefold()
                if any(word in text for word in success_words):
                    raise AssertionError(
                        f"success was announced before confirm: {event.data}\n\n"
                        f"{self.dump()}"
                    )

    def dump(self, limit: int = 400) -> str:
        lines: list[str] = []
        for event in self.events[-limit:]:
            payload = redact(json.dumps(event.data, ensure_ascii=False))
            if len(payload) > 700:
                payload = payload[:700] + "..."
            arrow = ">>" if event.direction == "out" else "<<"
            lines.append(f"#{event.seq:03d} {arrow} {payload}")
        if not lines:
            lines = ["(no events)"]
        if self._error:
            lines.append(f"receiver stopped: {self._error!r}")
        return "\n".join(lines)

    async def close(self) -> None:
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._ws.close(), timeout=5)


@contextlib.asynccontextmanager
async def console_client(server: AppServer) -> AsyncIterator[ConsoleClient]:
    websocket = await websockets.connect(server.ws_url, open_timeout=10,
                                         max_size=4 * 1024 * 1024)
    client = ConsoleClient(websocket)
    try:
        yield client
    finally:
        await client.close()


# --------------------------------------------------------------------------------------
# Session helpers for the safety chain
# --------------------------------------------------------------------------------------

def make_portal_session(site: FixtureSite | None = None, pending: bool = True) -> Any:
    from app.session import Session

    url = site.url("portal.html") if site else "http://127.0.0.1/portal.html"
    session = Session(profile=dict(PROFILE), state="READBACK",
                      approved_domains={"127.0.0.1"})
    session.locators = {
        "f1": "#full_name",
        "f2": "#dob",
        "f3": "#pin_code",
        "f4": "#aadhaar",
        "b1": "#submit",
    }
    session.expected = {
        "f1": {"label": "Full name", "selector": "#full_name",
               "value": PROFILE["full_name"], "type": "text",
               "source": "profile:full_name"},
        "f2": {"label": "Date of birth", "selector": "#dob",
               "value": PROFILE["dob"], "type": "date", "source": "profile:dob"},
        "f3": {"label": "PIN code", "selector": "#pin_code",
               "value": PROFILE["pin_code"], "type": "text",
               "source": "profile:pin_code"},
        "f4": {"label": "Aadhaar number", "selector": "#aadhaar",
               "value": PROFILE["aadhaar"], "type": "text",
               "source": "profile:aadhaar"},
    }
    if pending:
        session.pending_action = {
            "element_id": "b1",
            "label": "Submit application",
            "kind": "submit",
            "url": url,
            "domain": "127.0.0.1",
        }
    return session


def make_shop_session(site: FixtureSite | None = None) -> Any:
    session = make_portal_session(site=site, pending=False)
    session.pending_action = {
        "element_id": "b2",
        "label": "Place order",
        "kind": "pay",
        "url": site.url("shop.html") if site else "http://127.0.0.1/shop.html",
        "domain": "127.0.0.1",
        "site_id": "e2e_shop",
        "total": "249",
        "amount": "249",
    }
    return session


def actual_values(session: Any) -> dict[str, Any]:
    """Values in both id and label form, since build_readback may key either way."""
    values: dict[str, Any] = {}
    for field_id, expected in session.expected.items():
        values[field_id] = expected["value"]
        values[expected["label"]] = expected["value"]
    return values


def assert_readback_safe(chunks: Sequence[str]) -> None:
    """Check masking, the unmasked PIN code, and the exact final instruction."""
    assert chunks, "read-back returned no chunks"
    assert all(isinstance(chunk, str) for chunk in chunks), "read-back chunks must be strings"
    joined = "\n".join(chunks)
    assert_no_sensitive_text(joined, "read-back")

    pin_chunks = [chunk for chunk in chunks if "pin" in chunk.casefold()]
    assert pin_chunks, f"read-back has no PIN code chunk: {chunks!r}"
    pin_chunk = max(pin_chunks, key=lambda chunk: len(_digits(chunk)))
    pin_digits = _digits(pin_chunk)
    assert PROFILE["pin_code"] in pin_digits, (
        f"PIN code is not unmasked in read-back: {pin_chunk!r}"
    )

    aadhaar_chunks = [chunk for chunk in chunks if "aadhaar" in chunk.casefold()]
    assert aadhaar_chunks, f"read-back has no Aadhaar chunk: {chunks!r}"
    last_four = PROFILE["aadhaar"][-4:]
    masked = next(
        (chunk for chunk in reversed(aadhaar_chunks) if last_four in _digits(chunk)),
        aadhaar_chunks[-1],
    )
    assert last_four in _digits(masked), (
        f"Aadhaar last four digits are missing: {masked!r}"
    )
    assert PROFILE["aadhaar"] not in _digits(masked), (
        f"Aadhaar is unmasked in read-back: {masked!r}"
    )

    assert chunks[-1].strip() == CONFIRM_INSTRUCTION, (
        f"read-back must end with {CONFIRM_INSTRUCTION!r}, got {chunks[-1]!r}"
    )


def failure_with_log(exc: BaseException, client: ConsoleClient,
                     fake: FakeLLM | None = None) -> AssertionError:
    """Wrap an assertion with redacted Console and LLM diagnostics."""
    parts = [str(exc), "", "Console event log:", client.dump()]
    if fake is not None:
        parts.extend(["", "Scripted LLM calls:", fake.summary()])
    return AssertionError(redact("\n".join(parts)))
