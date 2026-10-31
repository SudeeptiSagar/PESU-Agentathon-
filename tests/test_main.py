"""CORE-11: the backend wiring: Console pages, the shared session, WebSocket events, origin check, shutdown."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import agent, config, main, tools
from app.main import app
from app.session import Session


# ---------------------------------------------------------------- fakes
class Page:
    url = "http://localhost:8000/portal/apply.html"

    async def title(self):
        return "Apply"


class FakeBrowser:
    def __init__(self, hub):
        self.hub, self.active, self.closed, self.started = hub, None, False, 0
        self.on_new_tab = None

    async def start(self):
        self.started += 1
        self.active = Page()

    async def close(self):
        self.closed = True


@pytest.fixture
def browsers():
    """Install a fake browser factory and a scripted model; returns the list of browsers made."""
    made = []

    def factory(hub):
        made.append(FakeBrowser(hub))
        return made[-1]
    app.state.browser_factory = factory
    return made


@pytest.fixture
def scripted(monkeypatch):
    """A scripted model: set `script` to a list of tool calls. Snapshots are faked."""
    state = type("S", (), {"script": [], "prompts": []})()

    async def fake_llm(messages, tool_schemas=None):
        state.prompts.append(messages)
        call = state.script.pop(0) if state.script else {"name": "finish", "args": {"summary": "ok"}}
        return {"text": None, "tool_call": call}

    async def fake_snapshot(page, session):
        snap = {"page_title": "Apply", "url": page.url, "domain": "localhost", "summary": "", "headings": [],
                "fields": [], "links": [{"id": "l1", "text": "Help"}], "tabs": [], "buttons": [], "errors": []}
        tools.record_snapshot(session, snap)
        session.locators["l1"] = "#l1"
        return snap

    async def no_challenge(page):
        return None
    monkeypatch.setattr(agent, "llm", fake_llm)
    monkeypatch.setattr(agent.tools, "take_snapshot", fake_snapshot)
    monkeypatch.setattr(agent.humancheck, "challenge_present", no_challenge)
    return state


def until(ws, predicate, limit=60):
    """Read events until one matches; returns (match, all events read)."""
    seen = []
    for _ in range(limit):
        event = ws.receive_json()
        seen.append(event)
        if predicate(event):
            return event, seen
    raise AssertionError(f"event never arrived; saw {seen}")


def is_state(name):
    return lambda e: e["type"] == "state" and e["name"] == name


# ---------------------------------------------------------------- pages
def test_health_reports_the_setup():
    body = TestClient(app).get("/health").json()
    assert body["status"] == "ok" and body["browser"] == config.BROWSER_MODE
    assert set(body) >= {"model", "tts", "stt", "gate", "console_built"}


def test_unbuilt_console_shows_the_placeholder(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DIST_DIR", tmp_path / "missing")
    client = TestClient(app)
    page = client.get("/console")
    assert page.status_code == 200 and "Voice Console" in page.text and "npm run build" in page.text
    assert client.get("/health").json()["console_built"] is False


def test_built_console_is_served_with_its_assets(monkeypatch, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "console.html").write_text("<html><title>Built Console</title></html>", encoding="utf-8")
    (tmp_path / "assets" / "console-abc.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "assets" / "console-abc.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not for the web", encoding="utf-8")
    monkeypatch.setattr(main, "DIST_DIR", tmp_path)
    client = TestClient(app)
    assert "Built Console" in client.get("/console").text
    js = client.get("/assets/console-abc.js")
    assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript")
    assert client.get("/assets/console-abc.css").headers["content-type"].startswith("text/css")
    assert client.get("/health").json()["console_built"] is True


@pytest.mark.parametrize("path", ["/assets/missing.js", "/assets/%2e%2e/secret.txt", "/assets/..%2fsecret.txt",
                                  "/assets/%2e%2e%2fconsole.html", "/assets/", "/assets/sub"])
def test_assets_cannot_escape_the_assets_folder(monkeypatch, tmp_path, path):
    (tmp_path / "assets" / "sub").mkdir(parents=True)
    (tmp_path / "console.html").write_text("x", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not for the web", encoding="utf-8")
    monkeypatch.setattr(main, "DIST_DIR", tmp_path)
    response = TestClient(app).get(path)
    assert response.status_code == 404 and "not for the web" not in response.text


# ---------------------------------------------------------------- the socket
def test_first_message_is_the_current_state():
    with TestClient(app).websocket_connect("/ws/console") as ws:
        assert ws.receive_json() == {"type": "state", "name": "IDLE"}


def test_a_typed_request_runs_through_the_agent_and_is_spoken(browsers, scripted):
    scripted.script = [{"name": "finish", "args": {"summary": "She was born in Karnal."}}]
    with TestClient(app).websocket_connect("/ws/console") as ws:
        ws.receive_json()
        ws.send_json({"type": "utterance", "text": "where was she born"})
        spoken, seen = until(ws, lambda e: e["type"] == "speak" and "Karnal" in e["text"])
        until(ws, is_state("DONE"))
    assert [e["name"] for e in seen if e["type"] == "state"] == ["PLANNING", "ACTING"]
    assert len(browsers) == 1 and browsers[0].started == 1


def test_no_browser_means_a_polite_answer_not_a_crash():
    with TestClient(app).websocket_connect("/ws/console") as ws:
        ws.receive_json()
        ws.send_json({"type": "utterance", "text": "find something"})
        event, _ = until(ws, lambda e: e["type"] == "speak")
        assert event["text"] == "The browser is not ready, so I can't do that yet."


def test_refreshing_the_console_keeps_one_session_and_one_browser(browsers, scripted):
    scripted.script = [{"name": "ask_user", "args": {"question": "Which one?"}}]
    client = TestClient(app)
    with client.websocket_connect("/ws/console") as ws:
        ws.receive_json()
        ws.send_json({"type": "utterance", "text": "pick one"})
        until(ws, lambda e: e["type"] == "speak" and e["text"] == "Which one?")
    with client.websocket_connect("/ws/console") as ws:                  # the Console page was reloaded
        assert ws.receive_json() == {"type": "state", "name": "NEEDS_USER"}   # same session, not a fresh one
        scripted.script = [{"name": "finish", "args": {"summary": "Done."}}]
        ws.send_json({"type": "utterance", "text": "the first one"})
        until(ws, is_state("DONE"))
    assert len(browsers) == 1


def test_two_consoles_both_hear_the_agent(browsers, scripted):
    scripted.script = [{"name": "finish", "args": {"summary": "Hello both."}}]
    client = TestClient(app)
    with client.websocket_connect("/ws/console") as a, client.websocket_connect("/ws/console") as b:
        a.receive_json()
        b.receive_json()
        a.send_json({"type": "utterance", "text": "say hello"})
        for ws in (a, b):
            until(ws, lambda e: e["type"] == "speak" and e["text"] == "Hello both.")


def test_escape_stops_and_space_toggles_pause(browsers, scripted):
    scripted.script = [{"name": "ask_user", "args": {"question": "Which?"}}]
    with TestClient(app).websocket_connect("/ws/console") as ws:
        ws.receive_json()
        ws.send_json({"type": "key", "name": "Space"})
        assert until(ws, lambda e: e["type"] == "speak")[0]["text"] == "There is nothing to pause."
        ws.send_json({"type": "utterance", "text": "pick one"})
        until(ws, is_state("NEEDS_USER"))
        ws.send_json({"type": "key", "name": "Escape"})
        until(ws, is_state("IDLE"))
        assert until(ws, lambda e: e["type"] == "speak")[0]["text"] == "Stopped."


@pytest.mark.parametrize("message", [
    {"type": "key", "name": "F13"}, {"type": "mystery"}, {"nothing": "here"}, ["not", "a", "dict"], "text", 5,
])
def test_unknown_messages_get_an_alert_and_the_connection_survives(message):
    with TestClient(app).websocket_connect("/ws/console") as ws:
        ws.receive_json()
        ws.send_json(message)
        event, _ = until(ws, lambda e: e["type"] == "alert")
        assert event["level"] == "warning"
        ws.send_json({"type": "key", "name": "Escape"})                  # still alive
        until(ws, is_state("IDLE"))


def test_invalid_json_is_survivable():
    with TestClient(app).websocket_connect("/ws/console") as ws:
        ws.receive_json()
        ws.send_text("{this is not json")
        event, _ = until(ws, lambda e: e["type"] == "alert")
        assert "could not read" in event["message"]
        ws.send_json({"type": "key", "name": "Escape"})
        until(ws, is_state("IDLE"))


@pytest.mark.parametrize("text", ["", "   ", None, 7, [], {}])
def test_empty_or_odd_utterances_are_ignored(text):
    with TestClient(app).websocket_connect("/ws/console") as ws:
        ws.receive_json()
        ws.send_json({"type": "utterance", "text": text})
        ws.send_json({"type": "key", "name": "Escape"})
        event, seen = until(ws, is_state("IDLE"))
        assert not [e for e in seen if e["type"] == "speak"]


def test_a_huge_utterance_is_refused(browsers, scripted):
    with TestClient(app).websocket_connect("/ws/console") as ws:
        ws.receive_json()
        ws.send_json({"type": "utterance", "text": "x" * (main.MAX_UTTERANCE_CHARS + 1)})
        event, _ = until(ws, lambda e: e["type"] == "alert")
        assert "too long" in event["message"] and scripted.prompts == []


def test_an_error_inside_the_agent_does_not_end_the_connection(monkeypatch):
    async def boom(text, ctx):
        raise RuntimeError("bug")
    monkeypatch.setattr(agent, "handle_utterance", boom)
    with TestClient(app).websocket_connect("/ws/console") as ws:
        ws.receive_json()
        ws.send_json({"type": "utterance", "text": "hello"})
        event, _ = until(ws, lambda e: e["type"] == "alert")
        assert event["level"] == "error" and "bug" not in event["message"]
        ws.send_json({"type": "key", "name": "Escape"})
        until(ws, is_state("IDLE"))


# ---------------------------------------------------------------- origin check
@pytest.mark.parametrize("origin", ["https://evil.example", "http://evil.example:8080", "null",
                                    "http://localhost:9999", "http://127.0.0.1.evil.example:8080",
                                    "https://localhost:8080"])
def test_a_web_page_from_another_origin_cannot_talk_to_the_agent(origin):
    with pytest.raises(WebSocketDisconnect):
        with TestClient(app).websocket_connect("/ws/console", headers={"origin": origin}):
            pass


@pytest.mark.parametrize("origin", [None, f"http://127.0.0.1:{config.PORT}", f"http://localhost:{config.PORT}",
                                    f"http://{config.HOST}:{config.PORT}/", "http://localhost:5173",
                                    "http://127.0.0.1:5173"])
def test_our_own_console_and_tools_are_accepted(origin):
    headers = {"origin": origin} if origin else {}
    with TestClient(app).websocket_connect("/ws/console", headers=headers) as ws:
        assert ws.receive_json()["type"] == "state"


def test_a_refused_origin_never_reaches_the_agent(browsers, scripted):
    with pytest.raises(WebSocketDisconnect):
        with TestClient(app).websocket_connect("/ws/console", headers={"origin": "https://evil.example"}) as ws:
            ws.send_json({"type": "utterance", "text": "confirm"})
    assert scripted.prompts == [] and browsers == [] and getattr(app.state, "hub", None) is None


# ---------------------------------------------------------------- the browser and shutdown
def test_new_tabs_are_announced_without_leaking_saved_values(monkeypatch):
    captured = {}

    class Capture:
        def __init__(self, on_new_tab=None, headless=False):
            captured.update(on_new_tab=on_new_tab, headless=headless)
    monkeypatch.setattr(main, "BrowserController", Capture)
    monkeypatch.setattr(config, "BROWSER_HEADLESS", True)
    hub = main.Hub(None)
    hub.ctx.session.profile = {"full_name": "Ramesh Kumar"}
    heard = []

    async def send(event):
        heard.append(event)
    hub.ctx.send = send
    main.make_browser(hub)
    assert captured["headless"] is True
    asyncio.run(captured["on_new_tab"]("Welcome Ramesh Kumar", "http://x"))
    assert heard == [{"type": "speak", "text": "A new tab opened: Welcome [saved full_name]"}]


def test_shutdown_stops_the_task_and_closes_the_browser(browsers, scripted):
    scripted.script = [{"name": "ask_user", "args": {"question": "Which?"}}]
    with TestClient(app) as client:                                       # runs startup and shutdown
        with client.websocket_connect("/ws/console") as ws:
            ws.receive_json()
            ws.send_json({"type": "utterance", "text": "pick one"})
            until(ws, is_state("NEEDS_USER"))
    assert browsers[0].closed is True
    assert getattr(app.state, "hub", None) is not None                    # (the fixture resets it for the next test)


def test_a_failing_browser_close_does_not_break_shutdown():
    class Stubborn:
        async def close(self):
            raise RuntimeError("already gone")
    hub = main.Hub(None)
    hub.ctx.browser = Stubborn()
    asyncio.run(hub.shutdown())          # must not raise


def test_a_dead_console_socket_is_dropped_not_fatal():
    class Dead:
        async def send_json(self, event):
            raise RuntimeError("gone")
    hub = main.Hub(None)
    dead = Dead()
    hub.sockets.add(dead)
    asyncio.run(hub.broadcast({"type": "speak", "text": "hi"}))
    assert hub.sockets == set()


def test_session_is_fresh_per_app_start_not_per_connection():
    hub = main.get_hub()
    assert isinstance(hub.ctx.session, Session) and main.get_hub() is hub
