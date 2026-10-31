"""Single entry point to the language model (PRD Section 12). Owner: M1.

Talks to Ollama's OpenAI-compatible endpoint. Swap the backend here (an API later)
without touching callers. Message contents are never logged (hard rule 4).
"""
import json
import logging

from openai import AsyncOpenAI

from app import config

log = logging.getLogger("app.llm")

_client: AsyncOpenAI | None = None

_RETRY_NOTE = (
    "Your last reply was not a valid tool call. Reply with exactly one call to one of the "
    "provided tools, using only its listed parameters and the correct types."
)
_JSON_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
               "array": list, "object": dict}


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=config.OLLAMA_URL, api_key="ollama", timeout=120.0)
    return _client


def _validate(name: str, args, tools: list[dict]) -> str | None:
    """Return None if (name, args) matches a schema in `tools`, else a short reason."""
    spec = next((t["function"] for t in tools if t["function"]["name"] == name), None)
    if spec is None:
        return f"unknown tool {name!r}"
    if not isinstance(args, dict):
        return "arguments are not a JSON object"
    params = spec.get("parameters", {})
    props = params.get("properties", {})
    for req in params.get("required", []):
        if req not in args:
            return f"missing argument {req!r}"
    for key, value in args.items():
        if key not in props:
            return f"unexpected argument {key!r}"
        want = _JSON_TYPES.get(props[key].get("type"))
        # bool is an int subclass in Python; do not accept True for an integer parameter
        if want and (not isinstance(value, want) or (want is int and isinstance(value, bool))):
            return f"argument {key!r} has the wrong type"
        if "enum" in props[key] and value not in props[key]["enum"]:
            return f"argument {key!r} is not one of the allowed values"
    return None


def _extract_call(message) -> tuple[str, object] | None:
    """Pull (name, args) from a chat message; args may still be invalid.

    Handles the standard tool_calls field, and small models that write the call as JSON
    in the text instead.
    """
    calls = getattr(message, "tool_calls", None)
    if calls:
        fn = calls[0].function
        try:
            return fn.name, json.loads(fn.arguments or "{}")
        except ValueError:
            return fn.name, None
    text = (message.content or "").strip()
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except ValueError:
            return None
        if isinstance(obj, dict) and "name" in obj:
            return obj["name"], obj.get("arguments", obj.get("args", {}))
    return None


async def _call(messages: list[dict], tools: list[dict] | None):
    kwargs = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": 0,
        # Ollama reads num_ctx from options; see docs/REFERENCE_NOTES.md / CORE-03 results
        # for whether this endpoint honours it on the installed Ollama version.
        "extra_body": {"options": {"num_ctx": config.NUM_CTX}},
    }
    if tools:
        kwargs["tools"] = tools
    resp = await _get_client().chat.completions.create(**kwargs)
    usage = getattr(resp, "usage", None)
    if usage is not None:
        log.info("llm prompt_tokens=%s completion_tokens=%s", usage.prompt_tokens,
                 usage.completion_tokens)
    return resp.choices[0].message


async def llm(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Call the model once.

    Returns {"text": str | None, "tool_call": {"name": str, "args": dict} | None}.
    With `tools`, a returned tool call is validated against them. A malformed call is
    retried once with a corrective note; if it is still invalid the result has
    tool_call=None and the caller treats that as a failed step.
    """
    msgs = list(messages)
    for attempt in (1, 2):
        message = await _call(msgs, tools)
        if not tools:
            return {"text": message.content, "tool_call": None}
        found = _extract_call(message)
        if found is None:
            # Plain text with tools offered: accept it as an answer, no retry needed.
            if (message.content or "").strip():
                return {"text": message.content, "tool_call": None}
            reason = "empty reply"
        else:
            name, args = found
            reason = _validate(name, args, tools)
            if reason is None:
                return {"text": message.content or None,
                        "tool_call": {"name": name, "args": args}}
        log.warning("llm malformed tool output (attempt %d): %s", attempt, reason)
        msgs = [*messages, {"role": "user", "content": f"{_RETRY_NOTE} Problem: {reason}."}]
    return {"text": None, "tool_call": None}
