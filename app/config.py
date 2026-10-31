"""Configuration from environment variables (.env), with defaults from PRD Section 7.

Owner: M1. Every other module reads settings from here, never from os.environ directly.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


# Server
HOST = _env("HOST", "127.0.0.1")
PORT = int(_env("PORT", "8080"))
ROOT = Path(__file__).resolve().parent.parent

# LLM (Ollama, OpenAI-compatible)
OLLAMA_URL = _env("OLLAMA_URL", "http://localhost:11434/v1")
LLM_MODEL = _env("LLM_MODEL", "qwen2.5:7b")
NUM_CTX = int(_env("NUM_CTX", "8192"))

# Search and autonomy
SEARCH_URL = _env("SEARCH_URL", "https://html.duckduckgo.com/html/?q={q}")
MAX_STEPS = int(_env("MAX_STEPS", "30"))
MAX_FAILURES = int(_env("MAX_FAILURES", "2"))
BLOCKED_DOMAINS: set[str] = {
    d.strip().lower() for d in _env("BLOCKED_DOMAINS", "").split(",") if d.strip()
}

# Gate (Jev)
GATE_BACKEND = _env("GATE_BACKEND", "rules")  # jev | llm | rules
GATE_THRESHOLDS = {
    "proceed": float(_env("GATE_PROCEED", "0.85")),  # p >= proceed -> proceed
    "ask": float(_env("GATE_ASK", "0.5")),           # ask <= p < proceed -> ask_user; below -> block
}

# Voice
STT_BACKEND = _env("STT_BACKEND", "handy")    # handy | whisper
TTS_BACKEND = _env("TTS_BACKEND", "browser")  # piper | browser
PIPER_VOICE = _env("PIPER_VOICE", "")

# Privacy (PRD Section 10, hard rule 4)
SENSITIVE_KEYS: frozenset[str] = frozenset({"aadhaar", "bank_account", "ifsc", "pin"})
PROFILE_PATH = Path(_env("PROFILE_PATH", str(Path.home() / ".voiceagent" / "profile.json")))
SITES_PATH = ROOT / "app" / "sites.json"
# STUB: CORE-04 (review defaults and add anything later tickets need)
