"""Single entry point to the language model (PRD Section 12). Owner: M1.

Talks to Ollama's native /api/chat, not the OpenAI-compatible /v1 endpoint: the /v1 endpoint
ignored options.num_ctx in the CORE-02 check (prompt silently cut to 2048 tokens), while the
native API takes num_ctx under "options". Swap the backend here (an API later) without
touching callers. Message contents are never logged (hard rule 4).
"""
import json
import logging

import httpx

from app import config

log = logging.getLogger("app.llm")

_RETRY_NOTE = (
    "Your last reply was not a valid tool call. Reply with exactly one call to one of the "
    "provided tools, using only its listed parameters and the correct types."
)
_JSON_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
               "array": list, "object": dict}


def _base_url() -> str:
    """OLLAMA_URL may end in /v1 (OpenAI-style); the native API lives one level up."""
    return config.OLLAMA_URL.rstrip("/").removesuffix("/v1")


async def _chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """POST one non-streaming request to /api/chat and return the response JSON."""
    payload: dict = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,  # no reasoning trace: faster steps, nothing extra to speak or parse
        "options": {"temperature": 0, "num_ctx": config.NUM_CTX},
    }
    if tools:
        payload["tools"] = tools
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{_base_url()}/api/chat", json=payload)
        if resp.status_code == 400 and "think" in resp.text.lower():
            # Model without thinking support: repeat without the flag.
            payload.pop("think")
            resp = await client.post(f"{_base_url()}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
    log.info("llm prompt_tokens=%s completion_tokens=%s",
             data.get("prompt_eval_count"), data.get("eval_count"))
    return data


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


def _extract_call(message: dict) -> tuple[str, object] | None:
    """Pull (name, args) from a chat message; args may still be invalid.

    Handles the standard tool_calls field, and small models that write the call as JSON
    in the text instead.
    """
    calls = message.get("tool_calls")
    if calls:
        fn = calls[0].get("function", {})
        args = fn.get("arguments", {})
        if isinstance(args, str):  # the native API sends an object; tolerate a string
            try:
                args = json.loads(args or "{}")
            except ValueError:
                args = None
        return fn.get("name", ""), args
    text = (message.get("content") or "").strip()
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except ValueError:
            return None
        if isinstance(obj, dict) and "name" in obj:
            return obj["name"], obj.get("arguments", obj.get("args", {}))
    return None


async def llm(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Call the model once.

    Returns {"text": str | None, "tool_call": {"name": str, "args": dict} | None}.
    With `tools`, a returned tool call is validated against them. A malformed call is
    retried once with a corrective note; if it is still invalid the result has
    tool_call=None and the caller treats that as a failed step.
    """
    msgs = list(messages)
    for attempt in (1, 2):
        message = (await _chat(msgs, tools)).get("message", {})
        content = message.get("content") or ""
        if not tools:
            return {"text": content, "tool_call": None}
        found = _extract_call(message)
        if found is None:
            # Plain text with tools offered: accept it as an answer, no retry needed.
            if content.strip():
                return {"text": content, "tool_call": None}
            reason = "empty reply"
        else:
            name, args = found
            reason = _validate(name, args, tools)
            if reason is None:
                return {"text": content or None, "tool_call": {"name": name, "args": args}}
        log.warning("llm malformed tool output (attempt %d): %s", attempt, reason)
        msgs = [*messages, {"role": "user", "content": f"{_RETRY_NOTE} Problem: {reason}."}]
    return {"text": None, "tool_call": None}
