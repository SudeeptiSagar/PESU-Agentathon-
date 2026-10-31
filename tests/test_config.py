"""CORE-04: config defaults, parsing and validation."""
import importlib

import dotenv
import pytest

from app import config

ENV_VARS = ["HOST", "PORT", "OLLAMA_URL", "LLM_MODEL", "NUM_CTX", "SEARCH_URL", "MAX_STEPS",
            "MAX_FAILURES", "BLOCKED_DOMAINS", "GATE_BACKEND", "GATE_PROCEED", "GATE_ASK",
            "JEV_API_KEY", "STT_BACKEND", "TTS_BACKEND", "PIPER_VOICE", "PROFILE_PATH"]


@pytest.fixture
def load(monkeypatch):
    """Reload config with a clean environment plus the given overrides; restore afterwards."""
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)  # ignore a local .env
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    def _load(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        return importlib.reload(config)

    yield _load
    monkeypatch.undo()
    importlib.reload(config)


def test_defaults_match_prd_section_7(load):
    c = load()
    assert c.OLLAMA_URL == "http://localhost:11434/v1"
    assert c.LLM_MODEL == "qwen3:8b"
    assert c.NUM_CTX == 8192
    assert c.MAX_STEPS == 30 and c.MAX_FAILURES == 2
    assert c.SEARCH_URL == "https://html.duckduckgo.com/html/?q={q}"
    assert c.BLOCKED_DOMAINS == set()
    assert c.GATE_BACKEND == "rules"
    assert c.GATE_THRESHOLDS == {"proceed": 0.85, "ask": 0.5}
    assert c.STT_BACKEND == "handy" and c.TTS_BACKEND == "browser" and c.PIPER_VOICE == ""
    assert c.JEV_API_KEY == ""
    assert c.PORT == 8080


def test_sensitive_keys(load):
    assert load().SENSITIVE_KEYS == {"aadhaar", "bank_account", "ifsc", "pin"}


def test_overrides_are_read(load):
    c = load(LLM_MODEL="qwen2.5:1.5b", MAX_STEPS="12", GATE_BACKEND="JEV", TTS_BACKEND="piper",
             GATE_PROCEED="0.9", GATE_ASK="0.4", JEV_API_KEY="abc",
             SEARCH_URL="http://localhost:8000/web/search.html?q={q}")
    assert c.LLM_MODEL == "qwen2.5:1.5b" and c.MAX_STEPS == 12
    assert c.GATE_BACKEND == "jev" and c.TTS_BACKEND == "piper"
    assert c.GATE_THRESHOLDS == {"proceed": 0.9, "ask": 0.4}
    assert c.JEV_API_KEY == "abc"
    assert "localhost:8000" in c.SEARCH_URL


def test_blocked_domains_are_trimmed_lowercased_and_skip_blanks(load):
    c = load(BLOCKED_DOMAINS=" Evil.example , ,BAD.test,")
    assert c.BLOCKED_DOMAINS == {"evil.example", "bad.test"}


def test_empty_value_falls_back_to_default(load):
    assert load(MAX_STEPS="  ").MAX_STEPS == 30


@pytest.mark.parametrize("env,fragment", [
    ({"MAX_STEPS": "abc"}, "MAX_STEPS"),
    ({"MAX_STEPS": "0"}, "MAX_STEPS"),
    ({"NUM_CTX": "100"}, "NUM_CTX"),
    ({"GATE_BACKEND": "jevv"}, "GATE_BACKEND"),
    ({"STT_BACKEND": "siri"}, "STT_BACKEND"),
    ({"TTS_BACKEND": "robot"}, "TTS_BACKEND"),
    ({"GATE_PROCEED": "high"}, "GATE_PROCEED"),
    ({"GATE_ASK": "0.9", "GATE_PROCEED": "0.5"}, "GATE_ASK"),
    ({"GATE_PROCEED": "1.5"}, "GATE_ASK"),
    ({"SEARCH_URL": "https://example.com/search"}, "SEARCH_URL"),
])
def test_invalid_values_raise_config_error_naming_the_variable(load, env, fragment):
    # Compare by name: reloading the module defines a new ConfigError class each time.
    with pytest.raises(ValueError, match=fragment) as err:
        load(**env)
    assert type(err.value).__name__ == "ConfigError"
