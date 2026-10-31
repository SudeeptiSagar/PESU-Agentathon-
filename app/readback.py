"""Spoken read-back from actual page values, and pending-action description.

Owner: M4 (Abishek). JEV-03.

Hard rule 4: Aadhaar, bank account, IFSC and the unlock PIN are masked to the last
four characters and never appear raw. `pin_code` is a POSTAL code, not a secret: it
is spoken digit by digit and never masked, so the demo's truncated PIN-code trap is
audible.
"""
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse

from app import config

#: Last chunk of every read-back. CORE-12 turns "confirm" into commit_pending.
CONFIRM_INSTRUCTION = "Say confirm to go ahead, or say change followed by the field name."

_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")

_DATE_WORDS = frozenset({"date", "dob", "birth", "birthday", "birthdate"})
_PHONE_WORDS = frozenset({"phone", "mobile", "telephone", "tel", "cell", "whatsapp"})
_POSTAL_WORDS = frozenset({"pincode", "postalcode", "zipcode"})
_POSTAL_NAMES = frozenset({"pincode", "postalcode", "zipcode", "zip"})

_ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T\s].*)?$")
_NUMERIC_DATE = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_NAMED_DATE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$")


def build_readback(session, actual_values: dict) -> list[str]:
    """Spoken chunks "Label: value", digits separated, sensitive values masked."""
    expected = getattr(session, "expected", None) or {}
    actual = actual_values if isinstance(actual_values, dict) else {}

    chunks: list[str] = []
    for field_id, raw_meta in expected.items():
        meta = raw_meta if isinstance(raw_meta, dict) else {}
        value = _lookup(actual, field_id, meta.get("value"))
        if _sensitive_key(field_id, meta):
            spoken = _masked(value)
        else:
            spoken = _formatted(field_id, meta, value)
        chunks.append(_sentence(meta.get("label") or field_id, spoken))
    chunks.append(CONFIRM_INSTRUCTION)
    return chunks


def describe_pending(session) -> str:
    """One sentence naming the held action, the site and any total shown."""
    pending = getattr(session, "pending_action", None)
    if not isinstance(pending, dict) or not pending:
        return "There is no action waiting for confirmation."

    label = _collapse(pending.get("label")) or _collapse(pending.get("kind")).capitalize() or "Submit"
    label = label.rstrip(" .!?") or "Submit"
    site = _site_name(pending)
    sentence = f"I'm about to press {label} on {site}."
    total = _total_clause(pending)
    return f"{sentence} {total}" if total else sentence


# ---------------------------------------------------------------- input values

def _lookup(actual_values: dict, field_id, fallback):
    """Real page value for field_id, accepting raw or {"value": ...}/{"actual": ...}."""
    try:
        present = field_id in actual_values
    except TypeError:
        present = False
    if present:
        value = actual_values[field_id]
        if isinstance(value, dict):
            for key in ("actual", "value"):
                if key in value:
                    value = value[key]
                    break
            else:
                value = None
        if value is not None:
            return value
    return fallback


def _collapse(value) -> str:
    """Collapse all whitespace runs to single spaces and trim."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def _formatted(field_id, meta: dict, value) -> str:
    raw = _collapse(value)
    if not raw:
        return ""
    kind = _kind(field_id, meta)
    if kind == "date":
        return _natural_date(raw) or raw
    if kind in {"phone", "pin_code"}:
        return _spaced_digits(raw) or raw
    return raw


def _sentence(label, value) -> str:
    name = _collapse(label).rstrip(" .:") or "Field"
    text = _collapse(value)
    if not text:
        return f"{name} is empty."
    if text[-1] not in ".!?":
        text += "."
    return f"{name}: {text}"


def _masked(value) -> str:
    """Mask a sensitive value to its last four characters, spoken one by one."""
    if value is None:
        return ""
    chars = [ch for ch in str(value) if ch.isalnum()]
    if not chars:
        return ""
    return "ending " + " ".join(chars[-4:])


def _spaced_digits(value) -> str:
    """"9876" -> "9 8 7 6" (same contract as voice.spoken_digits)."""
    return " ".join(ch for ch in str(value) if ch.isdigit())


# ------------------------------------------------------------ field semantics

def _token_list(*values) -> list[str]:
    tokens: list[str] = []
    for value in values:
        if value is None:
            continue
        tokens.extend(re.findall(r"[a-z0-9]+", str(value).lower()))
    return tokens


def _normalise(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _profile_key(meta: dict) -> str:
    """The profile key in source "profile:<key>", or ""."""
    source = str(meta.get("source") or "")
    _, _, key = source.partition(":")
    return key.strip().lower()


def _contains_run(tokens: list[str], parts: list[str]) -> bool:
    size = len(parts)
    return any(tokens[i:i + size] == parts for i in range(len(tokens) - size + 1))


def _category(field_id, meta: dict) -> str | None:
    """Return "postal", a sensitive key from config, or None.

    Matching is token based: field id, profile source key and (as a fallback) the
    label and input type. `pin_code` / `PIN code` is explicitly excluded from the
    sensitive keys, so it is never mistaken for the unlock PIN.
    """
    key = _profile_key(meta)
    identities = {_normalise(field_id), _normalise(key)} - {""}
    if identities & _POSTAL_NAMES:
        return "postal"

    sensitive = sorted(config.SENSITIVE_KEYS)
    for name in sensitive:
        if _normalise(name) in identities:
            return name

    tokens = _token_list(field_id, key, meta.get("label"), meta.get("type"))
    token_set = set(tokens)
    if token_set & _POSTAL_WORDS or "postal" in token_set:
        return "postal"
    if "pin" in token_set and "code" in token_set:
        return "postal"

    for name in sensitive:
        parts = name.split("_")
        if len(parts) == 1:
            if parts[0] in token_set:
                return name
        elif _contains_run(tokens, parts):
            return name
    return None


def _sensitive_key(field_id, meta: dict) -> str | None:
    category = _category(field_id, meta)
    return None if category in (None, "postal") else category


def _kind(field_id, meta: dict) -> str:
    if _category(field_id, meta) == "postal":
        return "pin_code"
    tokens = _token_list(meta.get("type"), _profile_key(meta), field_id, meta.get("label"))
    token_set = set(tokens)
    if str(meta.get("type") or "").lower() == "date" or token_set & _DATE_WORDS:
        return "date"
    if token_set & _PHONE_WORDS:
        return "phone"
    return "text"


# ------------------------------------------------------------------- dates

def _natural_date(text: str) -> str | None:
    """"1980-03-04" -> "4 March 1980"; returns None when the value is not a date."""
    match = _ISO_DATE.match(text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return _render_date(year, month, day)

    match = _NUMERIC_DATE.match(text)
    if match:
        first, second, year = (int(part) for part in match.groups())
        # Day first (Indian forms) unless that is impossible; then month first.
        for day, month in ((first, second), (second, first)):
            rendered = _render_date(year, month, day)
            if rendered:
                return rendered
        return None

    match = _NAMED_DATE.match(text)
    if match:
        day, month_name, year = match.groups()
        months = [name.lower() for name in _MONTHS]
        if month_name.lower() in months:
            return _render_date(int(year), months.index(month_name.lower()) + 1, int(day))
    return None


def _render_date(year: int, month: int, day: int) -> str | None:
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    return f"{parsed.day} {_MONTHS[parsed.month - 1]} {parsed.year}"


# ------------------------------------------------------------ pending action

def _site_name(pending: dict) -> str:
    site = _collapse(pending.get("site"))
    if site:
        return site.rstrip(" .")
    site_id = _collapse(pending.get("site_id"))
    if site_id:
        return _prettify(site_id)
    url = _collapse(pending.get("url"))
    if url:
        by_url = _site_for_url(url)
        if by_url:
            return by_url
    domain = _collapse(pending.get("domain"))
    if not domain:
        domain = _domain_from_url(url)
    if domain:
        return _site_for_domain(domain) or domain.rstrip(" .")
    return "this site"


def _prettify(value: str) -> str:
    """"demo_shop" -> "demo shop"."""
    return _collapse(re.sub(r"[_\-]+", " ", value)).lower()


def _domain_from_url(url: str) -> str:
    match = re.match(r"^[a-z][a-z0-9+.-]*://([^/?#]+)", url, re.IGNORECASE)
    if not match:
        return ""
    host = match.group(1).rsplit("@", 1)[-1].split(":", 1)[0]
    return host.lower()


def _load_sites() -> list[dict]:
    try:
        sites = json.loads(config.SITES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [site for site in sites if isinstance(site, dict)]


def _site_for_url(url: str) -> str | None:
    """Match a pending URL to a site by host and first path segment.

    Several demo sites share the `localhost` domain, so the domain alone cannot
    tell the shop from the portal. The URL path can: /web/... is the shop and
    /portal/... is the portal.
    """
    parsed = urlparse(url)
    host = _bare_domain(parsed.hostname or "")
    segments = [part for part in (parsed.path or "").split("/") if part]
    if not host or not segments:
        return None
    wanted = segments[0].lower()
    for site in _load_sites():
        site_url = urlparse(str(site.get("url") or ""))
        if _bare_domain(site_url.hostname or "") != host:
            continue
        site_segments = [part for part in (site_url.path or "").split("/") if part]
        if not site_segments or site_segments[0].lower() != wanted:
            continue
        name = site.get("id")
        if not name:
            aliases = site.get("aliases") or []
            name = aliases[0] if aliases else None
        if name:
            return _prettify(str(name))
    return None


def _site_for_domain(domain: str) -> str | None:
    """Read-only lookup of a display name in app/sites.json."""
    wanted = _bare_domain(domain)
    if not wanted:
        return None
    for site in _load_sites():
        if _bare_domain(site.get("domain")) != wanted:
            continue
        name = site.get("id")
        if not name:
            aliases = site.get("aliases") or []
            name = aliases[0] if aliases else None
        if name:
            return _prettify(str(name))
    return None


def _bare_domain(value) -> str:
    domain = _collapse(value).lower().rstrip(".")
    return domain[4:] if domain.startswith("www.") else domain


def _total_clause(pending: dict) -> str:
    for key in ("total", "amount", "total_text"):
        if key not in pending:
            continue
        raw = pending[key]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        if key == "total_text":
            text = _collapse(raw).rstrip(" .")
            if text:
                return f"Total {text}."
            continue
        amount = _as_decimal(raw)
        if amount is not None:
            return f"Total {_indian_number(amount)} rupees."
        text = _collapse(raw).rstrip(" .")
        if text:
            return f"Total {text}."
    return ""


def _as_decimal(value) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, (int, float)):
        amount = Decimal(str(value))
    elif isinstance(value, str):
        text = value.strip()
        text = re.sub(r"^(?:₹|rs\.?|inr)\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*(?:rupees|rs\.?|inr)$", "", text, flags=re.IGNORECASE)
        text = text.replace(",", "").strip()
        try:
            amount = Decimal(text)
        except InvalidOperation:
            return None
    else:
        return None
    return amount if amount.is_finite() else None


def _indian_number(amount: Decimal) -> str:
    """"249" -> "249"; "249.5" -> "249.50"; "1234567" -> "12,34,567"."""
    negative = amount < 0
    amount = abs(amount)
    if amount == amount.to_integral_value():
        whole, fraction = str(int(amount)), ""
    else:
        rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        whole, _, fraction = f"{rounded:f}".partition(".")
    number = _group_indian(whole) + (f".{fraction}" if fraction else "")
    return f"-{number}" if negative else number


def _group_indian(digits: str) -> str:
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])
