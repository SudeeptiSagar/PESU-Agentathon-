"""Single entry point to the language model (PRD Section 12). Owner: M1.

Swap the backend here (Ollama by default, an API later) without touching callers.
"""


async def llm(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Call the model once.

    Returns {"text": str | None, "tool_call": {"name": str, "args": dict} | None}.
    The tool call, when present, is validated against `tools`.
    """
    # STUB: CORE-02 (Ollama OpenAI-compatible endpoint, temperature 0, num_ctx, one retry)
    if tools:
        return {"text": None, "tool_call": {"name": "read_page", "args": {"mode": "summary"}}}
    return {"text": "Okay.", "tool_call": None}
