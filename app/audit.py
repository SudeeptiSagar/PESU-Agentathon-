"""JSONL audit log with sensitive keys dropped (PRD FR-19). Owner: M4 (Abishek).

CORE-01 contract stub; replace the body, keep the signature.
"""


def log_event(kind: str, **fields) -> None:
    """Append one event to the audit log. Drops config.SENSITIVE_KEYS automatically."""
    # STUB: JEV-06
    return None
