"""Gate on proposed actions: proceed, ask_user or block (PRD Section 10).

Owner: M4 (Abishek). CORE-01 contract stub; replace the body, keep the signature.
"""


async def check(action: dict, context: dict) -> dict:
    """context: {"goal","domain","approved_domains","element","history_tail"}.

    Returns {"decision": "proceed"|"ask_user"|"block", "reason": str, "p": float}.
    """
    # STUB: JEV-04, JEV-05
    element = context.get("element") or {}
    if element.get("irreversible"):
        return {"decision": "ask_user", "reason": "irreversible control", "p": 0.5}
    return {"decision": "proceed", "reason": "stub", "p": 0.95}
