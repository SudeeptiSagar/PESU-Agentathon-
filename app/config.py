"""Configuration from environment variables (.env), with defaults from PRD Section 7.

Owner: M1. Every other module reads settings from here, never from os.environ directly.
Bad values fail at startup with a ConfigError that names the variable.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class ConfigError(ValueError):
    """An environment variable has an invalid value."""


def _env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _int(name: str, default: int, minimum: int = 1) -> int:
    raw = _env(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}") from None
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}, got {value}")
    return value


def _float(name: str, default: float) -> float:
    raw = _env(name, str(default))
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None


def _choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = _env(name, default).lower()
    if value not in allowed:
        raise ConfigError(f"{name} must be one of {', '.join(allowed)}, got {value!r}")
    return value


# Server
HOST = _env("HOST", "127.0.0.1")
PORT = _int("PORT", 8080)
ROOT = Path(__file__).resolve().parent.parent

# LLM (Ollama native /api/chat; OLLAMA_URL may end in /v1, which is stripped)
OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434/v1")
LLM_MODEL = _env("LLM_MODEL", "qwen3:8b")
NUM_CTX = _int("NUM_CTX", 8192, minimum=512)

# Search and autonomy
SEARCH_URL = _env("SEARCH_URL", "https://html.duckduckgo.com/html/?q={q}")
if "{q}" not in SEARCH_URL:
    raise ConfigError("SEARCH_URL must contain the {q} placeholder")
MAX_STEPS = _int("MAX_STEPS", 30)
MAX_FAILURES = _int("MAX_FAILURES", 2)
BLOCKED_DOMAINS: set[str] = {
    d.strip().lower() for d in _env("BLOCKED_DOMAINS", "").split(",") if d.strip()
}

# Gate (Jev)
GATE_BACKEND = _choice("GATE_BACKEND", "rules", ("jev", "llm", "rules"))
GATE_THRESHOLDS = {
    "proceed": _float("GATE_PROCEED", 0.85),  # p >= proceed -> proceed
    "ask": _float("GATE_ASK", 0.5),           # ask <= p < proceed -> ask_user; below -> block
}
if not 0 <= GATE_THRESHOLDS["ask"] <= GATE_THRESHOLDS["proceed"] <= 1:
    raise ConfigError("need 0 <= GATE_ASK <= GATE_PROCEED <= 1")
JEV_API_KEY = _env("JEV_API_KEY", "")  # never log or print this

# Voice
STT_BACKEND = _choice("STT_BACKEND", "handy", ("handy", "whisper"))
TTS_BACKEND = _choice("TTS_BACKEND", "browser", ("piper", "browser"))
PIPER_VOICE = _env("PIPER_VOICE", "")

# Privacy (PRD Section 10, hard rule 4). "pin" is the app unlock PIN; the postal
# code field is "pin_code" and is not sensitive.
SENSITIVE_KEYS: frozenset[str] = frozenset({"aadhaar", "bank_account", "ifsc", "pin"})
PROFILE_PATH = Path(_env("PROFILE_PATH", str(Path.home() / ".voiceagent" / "profile.json")))
SITES_PATH = ROOT / "app" / "sites.json"
