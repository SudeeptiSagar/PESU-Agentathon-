"""Check app/llm.py against a real Ollama (CORE-02). Owner: M1.

Run from the repo root with the venv active:  python scripts/check_llm.py
Reads OLLAMA_URL, LLM_MODEL, NUM_CTX from .env or the environment. Exits 1 if any check fails.
No profile data is used; prompts contain only made-up text.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import config  # noqa: E402
from app import llm as llm_mod  # noqa: E402
from app.tools import TOOL_SCHEMAS  # noqa: E402

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


async def check_reachable() -> bool:
    base = config.OLLAMA_URL.rstrip("/").removesuffix("/v1")
    try:
        r = httpx.get(f"{base}/api/tags", timeout=5)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001 - report any failure plainly
        record("ollama reachable", False, f"{base}: {type(e).__name__}: {e}")
        return False
    names = [m["name"] for m in r.json().get("models", [])]
    wanted = config.LLM_MODEL
    have = wanted in names or any(n.split(":")[0] == wanted and ":" not in wanted for n in names)
    record("ollama reachable", True, f"{base}, models: {', '.join(names) or 'none'}")
    record("model installed", have, f"LLM_MODEL={wanted}" + ("" if have else f" (run: ollama pull {wanted})"))
    return have


async def check_plain() -> None:
    try:
        out = await llm_mod.llm([{"role": "user", "content": "Reply with the single word: ready"}])
        record("plain text reply", bool(out["text"]), repr((out["text"] or "")[:60]))
    except Exception as e:  # noqa: BLE001
        record("plain text reply", False, f"{type(e).__name__}: {e}")


async def check_tool_call() -> None:
    msgs = [
        {"role": "system", "content": "You control a web browser. Call exactly one tool. "
         "Fill form fields only with placeholders like {dob}, never real values."},
        {"role": "user", "content": "Page fields: f1 'Full name', f2 'Date of birth'. "
         "Fill the date of birth field from the user's profile."},
    ]
    try:
        out = await llm_mod.llm(msgs, TOOL_SCHEMAS)
        call = out["tool_call"]
        ok = bool(call) and call["name"] == "fill_field" and call["args"].get("field_id") == "f2"
        record("tool call (fill_field f2)", ok, str(call) if call else f"no tool call, text={out['text']!r}")
    except Exception as e:  # noqa: BLE001
        record("tool call (fill_field f2)", False, f"{type(e).__name__}: {e}")


async def check_num_ctx() -> None:
    """Send ~6000 tokens. If num_ctx is ignored, Ollama truncates to its default (2048 to 4096)."""
    needle = "The secret code is PINEAPPLE-42."
    filler = "alpha bravo charlie delta echo foxtrot golf hotel india juliet. " * 500
    msgs = [{"role": "user", "content": f"{needle}\n{filler}\nWhat is the secret code? Answer with the code only."}]
    try:
        data = await llm_mod._chat(msgs)
        used = data.get("prompt_eval_count", 0)
        answer = data.get("message", {}).get("content") or ""
        ok = used > 4096 and "PINEAPPLE-42" in answer
        detail = f"NUM_CTX={config.NUM_CTX}, prompt_tokens={used}, needle recalled={'PINEAPPLE-42' in answer}"
        if not ok:
            detail += " -> num_ctx looks IGNORED; check the Ollama version (ollama --version) and report it"
        record("num_ctx honoured", ok, detail)
    except Exception as e:  # noqa: BLE001
        record("num_ctx honoured", False, f"{type(e).__name__}: {e}")


async def main() -> int:
    print(f"OLLAMA_URL={config.OLLAMA_URL} LLM_MODEL={config.LLM_MODEL} NUM_CTX={config.NUM_CTX}\n")
    if await check_reachable():
        await check_plain()
        await check_tool_call()
        await check_num_ctx()
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
