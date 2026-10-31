"""LLM tool schemas, tool executor and domain policy (PRD Sections 10 and 12). Owner: M1.

Hard rules enforced here: placeholders only (1), irreversible controls held as
session.pending_action and never clicked (2), domain policy in code (3), no raw sensitive
values in results (4). There is deliberately NO submit or commit tool for the LLM.
"""
import json
from urllib.parse import urlparse

from app import config
from app.session import Session


def _tool(name: str, description: str, **params: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": params,
                           "required": list(params)},
        },
    }


_S = {"type": "string"}
_I = {"type": "integer"}

TOOL_SCHEMAS: list[dict] = [
    _tool("navigate", "Open a known site by name (alias) or a URL.", target=_S),
    _tool("web_search", "Search the web for a query.", query=_S),
    _tool("go_back", "Go back to the previous page."),
    _tool("scroll", "Scroll the page.", direction={"type": "string", "enum": ["up", "down"]}),
    _tool("read_page", "Read the current page.",
          mode={"type": "string", "enum": ["summary", "main_text", "fields"]}),
    _tool("click", "Click a link or button by its element id.", element_id=_S),
    _tool("type_text", "Type non-sensitive text from the user or the task into a field.",
          field_id=_S, text=_S),
    _tool("fill_field", "Fill a field from the user's profile using a placeholder like {dob}.",
          field_id=_S, value_ref=_S),
    _tool("select_option", "Choose an option in a dropdown.", field_id=_S, option=_S),
    _tool("press_key", "Press a keyboard key, such as Enter or Tab.", key=_S),
    _tool("switch_tab", "Switch to a browser tab by index.", index=_I),
    _tool("close_tab", "Close a browser tab by index.", index=_I),
    _tool("ask_user", "Ask the user a short question and wait for the answer.", question=_S),
    _tool("speak", "Say a short progress message to the user.", text=_S),
    _tool("finish", "Finish the task with a spoken summary.", summary=_S),
]
TOOL_NAMES = frozenset(t["function"]["name"] for t in TOOL_SCHEMAS)


def _load_sites() -> list[dict]:
    try:
        return json.loads(config.SITES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def resolve_target(target: str) -> dict:
    """Map a sites.json alias, URL or bare domain to {"url","domain","site_id","trusted"}."""
    # STUB: CORE-09 (full alias matching and phrasings; web_search fallback in the agent)
    t = target.strip().lower()
    for site in _load_sites():
        if t == site["id"] or t in site.get("aliases", []):
            return {"url": site["url"], "domain": site["domain"],
                    "site_id": site["id"], "trusted": bool(site.get("trusted"))}
    url = target if "://" in target else f"https://{target}"
    return {"url": url, "domain": (urlparse(url).hostname or "").lower(),
            "site_id": None, "trusted": False}


def domain_allowed(domain: str) -> bool:
    """False if the domain or a parent domain is in BLOCKED_DOMAINS."""
    d = domain.lower().rstrip(".")
    return not any(d == b or d.endswith("." + b) for b in config.BLOCKED_DOMAINS)


class ToolExecutor:
    """Runs one validated LLM tool call against the browser."""

    async def run(self, action: dict, session: Session, browser) -> str:
        """Execute action {"name", "args"}. Returns a short result with no raw sensitive values."""
        # STUB: CORE-08 (placeholders, domain policy, expected values, irreversible hold)
        name = action.get("name")
        if name not in TOOL_NAMES:
            return f"error: unknown tool {name!r}"
        return f"ok: {name}"


async def commit_pending(session: Session, browser) -> str:
    """Run the held irreversible action. Called by the state machine only, after "confirm"."""
    # STUB: CORE-12
    if not (session.confirmed and session.pending_action):
        raise PermissionError("commit_pending needs confirmed=True and a pending_action")
    label = session.pending_action.get("label", "the action")
    session.pending_action = None
    session.confirmed = False
    return f"ok: pressed {label}"
