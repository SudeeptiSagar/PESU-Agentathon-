"""Spoken read-back from actual page values, and pending-action description.

Owner: M4 (Abishek). CORE-01 contract stubs; replace the bodies, keep the signatures.
"""


def build_readback(session, actual_values: dict) -> list[str]:
    """Spoken chunks "Label: value", digits separated, sensitive values masked to the last four."""
    # STUB: JEV-03
    return ["Full name: Ramesh Kumar",
            "Say confirm to go ahead, or say change followed by the field name."]


def describe_pending(session) -> str:
    """One sentence naming the held action, the site and any total shown."""
    # STUB: JEV-03
    pa = session.pending_action or {}
    return f"I'm about to press {pa.get('label', 'Submit')} on {pa.get('domain', 'this site')}."
