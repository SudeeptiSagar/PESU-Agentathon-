"""CORE-01 smoke test: every module imports and exposes its contract; /health and WS echo work."""
import importlib
import inspect

import pytest
from fastapi.testclient import TestClient

MODULES = ["config", "session", "llm", "profile", "tools", "agent", "main", "voice",
           "onboarding", "browser", "perception", "humancheck", "gate", "verifier",
           "readback", "audit"]

CONTRACT = {
    "llm": ["llm"], "session": ["Session", "transition"],
    "profile": ["profile_exists", "save_profile", "load_profile", "WrongPinError"],
    "tools": ["TOOL_SCHEMAS", "ToolExecutor", "resolve_target", "domain_allowed", "commit_pending"],
    "agent": ["handle_utterance", "run_task", "stop"],
    "voice": ["STT", "HandyConsoleSTT", "WhisperSTT", "TTS", "PiperTTS", "BrowserTTS",
              "match_command", "spoken_digits", "words_to_digits"],
    "onboarding": ["run_onboarding", "run_unlock"], "browser": ["BrowserController"],
    "perception": ["snapshot", "main_text"], "humancheck": ["challenge_present"],
    "gate": ["check"], "verifier": ["verify"],
    "readback": ["build_readback", "describe_pending"], "audit": ["log_event"],
    "config": ["OLLAMA_URL", "LLM_MODEL", "NUM_CTX", "MAX_STEPS", "MAX_FAILURES", "SEARCH_URL",
               "BLOCKED_DOMAINS", "GATE_BACKEND", "GATE_THRESHOLDS", "STT_BACKEND",
               "TTS_BACKEND", "PIPER_VOICE", "SENSITIVE_KEYS"],
}


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    mod = importlib.import_module(f"app.{name}")
    for attr in CONTRACT.get(name, []):
        assert hasattr(mod, attr), f"app.{name} is missing {attr}"


def test_async_contract():
    from app import agent, gate, humancheck, llm, perception, tools, verifier
    for fn in [llm.llm, agent.handle_utterance, agent.run_task, agent.stop, tools.commit_pending,
               tools.ToolExecutor.run, perception.snapshot, perception.main_text,
               humancheck.challenge_present, gate.check, verifier.verify]:
        assert inspect.iscoroutinefunction(fn), fn.__qualname__


def test_no_submit_or_commit_tool():
    from app.tools import TOOL_NAMES
    assert not {n for n in TOOL_NAMES if "submit" in n or "commit" in n}


def test_health():
    from app.main import app
    r = TestClient(app).get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_console_page():
    from app.main import app
    r = TestClient(app).get("/console")
    assert r.status_code == 200 and "Voice Console" in r.text


def test_ws_echo_and_stop():
    from app.main import app
    with TestClient(app).websocket_connect("/ws/console") as ws:
        assert ws.receive_json() == {"type": "state", "name": "IDLE"}
        ws.send_json({"type": "utterance", "text": "hello"})
        # CORE-10: the agent answers instead of echoing. No browser is wired in yet (CORE-11).
        assert ws.receive_json() == {"type": "speak",
                                     "text": "The browser is not ready, so I can't do that yet."}
        ws.send_json({"type": "key", "name": "Escape"})
        assert ws.receive_json() == {"type": "input_mode", "mode": "voice"}      # stop never leaves hidden-entry mode on
        assert ws.receive_json() == {"type": "state", "name": "IDLE"}
        assert ws.receive_json() == {"type": "speak", "text": "Stopped."}
