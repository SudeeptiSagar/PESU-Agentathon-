"""JSONL audit log with sensitive keys dropped (PRD FR-19). Owner: M4 (Abishek).

One compact UTF-8 JSON object per line, appended to ``LOG_PATH`` outside the
repo. Sensitive keys are dropped before serialisation and identifier-like
values (Aadhaar, account and card numbers, IFSC) are masked to their last four
characters, so a caller bug cannot leak them through this module.
"""

import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import config

logger = logging.getLogger(__name__)

# Module-level so tests and callers can redirect the log without touching config.
# Default lives next to the encrypted profile, outside the repository.
LOG_PATH: Path = Path(config.PROFILE_PATH).parent / "audit.jsonl"

_LOCK = threading.Lock()
_MAX_DEPTH = 20
_MASK = "*"

# Beyond config.SENSITIVE_KEYS. Stored already normalised.
_EXTRA_SENSITIVE_KEYS = frozenset({
    "pin_value", "unlock_pin", "aadhaar_number", "aadhaar_no",
    "bank_account_no", "bank_account_number", "account_number", "ifsc_code",
    "api_key", "apikey", "jev_api_key", "typesafe_api_key", "token",
    "access_token", "password", "passwd", "secret", "otp", "cvv", "card_number",
})

# Keys that contain a sensitive token but are not sensitive themselves. In
# particular "pin" is the app unlock PIN, while "pin_code" is a postal code.
_SAFE_KEYS = frozenset({"pin_code", "pin_codes", "pincode", "pincodes"})

# A sensitive word as a whole underscore-separated token, never a substring:
# "user_pin" is dropped, "spin_code" and "pincode" are not.
_SENSITIVE_TOKENS = frozenset({
    "aadhaar", "aadhar", "pin", "ifsc", "password", "passwd", "secret",
    "otp", "cvv", "token",
})

# Compound names where neither word alone is enough ("bank" alone is a name).
_SENSITIVE_PAIRS = (
    ("bank", "account"),
    ("account", "number"),
    ("card", "number"),
    ("api", "key"),
)

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_KEY_SEPARATORS = re.compile(r"[^a-z0-9]+")

# 12 or more consecutive digits, or 3-4 groups of four digits joined by spaces
# or hyphens (Aadhaar "1234 5678 9012", card "4111 1111 1111 1111").
# The lookarounds keep field ids such as "f3" and alphanumeric ids intact.
_PLAIN_DIGITS = re.compile(r"(?<![0-9A-Za-z])\d{12,}(?![0-9A-Za-z])")
_GROUPED_DIGITS = re.compile(
    r"(?<![0-9A-Za-z])\d{4}[ -]\d{4}[ -]\d{4}(?:[ -]\d{4})?(?![0-9A-Za-z])"
)
_IFSC = re.compile(r"(?<![A-Za-z0-9])[A-Z]{4}0[A-Z0-9]{6}(?![A-Za-z0-9])")


def _normalise_key(key: Any) -> str:
    """Lowercase a key and make separators underscores (bankAccount -> bank_account)."""
    text = str(key).strip()
    if not text:
        return ""
    text = _CAMEL_BOUNDARY.sub("_", text)
    return _KEY_SEPARATORS.sub("_", text.lower()).strip("_")


def _sensitive_names() -> frozenset[str]:
    """Config keys plus the fixed extras, normalised, read at call time."""
    configured = {_normalise_key(key) for key in config.SENSITIVE_KEYS}
    return frozenset(configured) | _EXTRA_SENSITIVE_KEYS


def _is_sensitive_key(key: Any, sensitive: frozenset[str]) -> bool:
    """Exact or whole-token match, so "pin_code" survives and "monkey" is safe."""
    name = _normalise_key(key)
    if not name or name in _SAFE_KEYS:
        return False
    if name in sensitive:
        return True
    if name.endswith(("_api_key", "_api_keys", "apikey", "apikeys")):
        return True
    tokens = name.split("_")
    if any(token in _SENSITIVE_TOKENS for token in tokens):
        return True
    token_set = set(tokens)
    return any(first in token_set and second in token_set for first, second in _SENSITIVE_PAIRS)


def _mask_digits(digits: str) -> str:
    """Keep the last four digits, mask the rest with stars (length preserved)."""
    if len(digits) <= 4:
        return digits
    return _MASK * (len(digits) - 4) + digits[-4:]


def _mask_grouped(match: re.Match[str]) -> str:
    """Mask a grouped number while keeping its spaces or hyphens in place."""
    text = match.group(0)
    masked = iter(_mask_digits("".join(char for char in text if char.isdigit())))
    return "".join(next(masked) if char.isdigit() else char for char in text)


def _mask_tail(text: str) -> str:
    """Mask everything but the last four characters (IFSC codes)."""
    if len(text) <= 4:
        return text
    return _MASK * (len(text) - 4) + text[-4:]


def _scrub_text(value: Any) -> str:
    """Redact the configured Jev key and mask identifier-like runs in a string."""
    text = value if isinstance(value, str) else str(value)
    api_key = getattr(config, "JEV_API_KEY", "") or ""
    if isinstance(api_key, str) and len(api_key) >= 4:
        text = text.replace(api_key, "[redacted]")
    text = _IFSC.sub(lambda match: _mask_tail(match.group(0)), text)
    text = _GROUPED_DIGITS.sub(_mask_grouped, text)
    text = _PLAIN_DIGITS.sub(lambda match: _mask_digits(match.group(0)), text)
    return text


def _sanitize(value: Any, sensitive: frozenset[str], depth: int) -> Any:
    """Recursively copy dicts, lists, tuples and sets, dropping sensitive keys."""
    if depth > _MAX_DEPTH:
        return "<max-depth>"
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key, sensitive):
                continue
            name = key if isinstance(key, str) else _scrub_text(key)
            cleaned[name] = _sanitize(item, sensitive, depth + 1)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, sensitive, depth + 1) for item in value]
    if isinstance(value, (set, frozenset)):
        # Sets have no JSON form; sort for a stable log line.
        return [_sanitize(item, sensitive, depth + 1) for item in sorted(value, key=repr)]
    if isinstance(value, str):
        return _scrub_text(value)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        digits = str(abs(value))
        if len(digits) >= 12:
            masked = _mask_digits(digits)
            return f"-{masked}" if value < 0 else masked
        return value
    if isinstance(value, float):
        return value
    # datetime, Decimal, Path and other objects: stringify, then scrub.
    return _scrub_text(value)


def _utc_now() -> str:
    """Current UTC time as ISO-8601 with millisecond precision."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def log_event(kind: str, **fields) -> None:
    """Append one event to the audit log. Drops config.SENSITIVE_KEYS automatically."""
    try:
        sensitive = _sensitive_names()
        record: dict[str, Any] = {"ts": _utc_now(), "kind": _scrub_text(kind)}
        for key, value in _sanitize(fields, sensitive, 0).items():
            if key not in record:  # never let a field override ts or kind
                record[key] = value
        line = json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), default=str
        ) + "\n"
    except Exception:  # never let auditing break the caller
        logger.warning("audit: could not build event %r", kind, exc_info=True)
        return

    target = LOG_PATH
    try:
        path = Path(target)
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()
    except Exception:
        logger.warning("audit: could not write event to %s", target, exc_info=True)
