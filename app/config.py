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


def _bool(name: str, default: bool) -> bool:
    raw = _env(name, "true" if default else "false").lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be true or false, got {raw!r}")


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

# Browser (BRW-02, BRW-07).
#  chromium: Playwright's bundled Chromium, fresh each time (default; tests and the offline demo)
#  chrome:   the backend starts the installed Chrome with remote debugging on 127.0.0.1 and a
#            persistent agent profile, then attaches over CDP. Sign in to sites once; later
#            sessions are already logged in.
#  attach:   attach to a Chrome that is already running with remote debugging on.
BROWSER_MODE = _choice("BROWSER_MODE", "chromium", ("chromium", "chrome", "attach"))
# True runs Playwright's Chromium without windows (tests, servers). The demo uses visible windows.
BROWSER_HEADLESS = _bool("BROWSER_HEADLESS", False)
CHROME_PATH = _env("CHROME_PATH", "")  # empty = auto-detect the installed Chrome
CHROME_DEBUG_PORT = _int("CHROME_DEBUG_PORT", 9222, minimum=1024)
if CHROME_DEBUG_PORT > 65535:
    raise ConfigError(f"CHROME_DEBUG_PORT must be at most 65535, got {CHROME_DEBUG_PORT}")
CDP_URL = f"http://127.0.0.1:{CHROME_DEBUG_PORT}"  # local only: the debug port controls the browser
# Holds logged-in sessions, so it must never be inside the repo (it could be committed).
AGENT_PROFILE_DIR = Path(_env("AGENT_PROFILE_DIR", str(Path.home() / ".voiceagent" / "chrome-profile")))
_profile_dir = AGENT_PROFILE_DIR.resolve()
if _profile_dir == ROOT.resolve() or ROOT.resolve() in _profile_dir.parents:
    raise ConfigError("AGENT_PROFILE_DIR must be outside the repository")

# Privacy (PRD Section 10, hard rule 4). "pin" is the app unlock PIN; the postal
# code field is "pin_code" and is not sensitive.
SENSITIVE_KEYS: frozenset[str] = frozenset({"aadhaar", "bank_account", "ifsc", "pin"})
PROFILE_PATH = Path(_env("PROFILE_PATH", str(Path.home() / ".voiceagent" / "profile.json")))
SITES_PATH = ROOT / "app" / "sites.json"
