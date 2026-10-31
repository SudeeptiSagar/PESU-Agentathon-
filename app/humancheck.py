"""Detects pages that need a human: CAPTCHA, OTP, password, payment (PRD Section 10).

Owner: M3 (Sudeepti). CORE-01 contract stub; replace the body, keep the signature.
"""


async def challenge_present(page) -> dict | None:
    """Return {"kind": "captcha"|"otp"|"password"|"payment", "hint": str}, or None."""
    # STUB: BRW-04
    return None
