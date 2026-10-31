"""Page perception: compact snapshot and readable main text (PRD Section 12).

Owner: M3 (Sudeepti). CORE-01 contract stubs; replace the bodies, keep the signatures.
"""


async def snapshot(page, session) -> dict:
    """Compact page state for the LLM. Fills session.locators[id]. Caps: 60 elements, labels < 60 chars.

    buttons[].kind is submit|pay|send|post|delete|accept|other.
    """
    # STUB: BRW-03, BRW-08
    session.locators.update({"f1": "#full_name", "f2": "#dob", "l1": "a#apply", "b1": "#submit"})
    return {
        "page_title": "Disability Pension - Apply",
        "url": "http://localhost:8000/portal/apply.html",
        "domain": "localhost",
        "summary": "Application form with Personal Details and Bank Details tabs.",
        "headings": ["Apply for Disability Pension", "Personal Details"],
        "fields": [
            {"id": "f1", "label": "Full name", "type": "text", "required": True,
             "value": "", "error": None, "sensitive_hint": False},
            {"id": "f2", "label": "Date of birth", "type": "date", "required": True,
             "value": "", "error": None, "sensitive_hint": False},
        ],
        "links": [{"id": "l1", "text": "Help"}],
        "tabs": [{"id": "t1", "text": "Personal Details", "selected": True},
                 {"id": "t2", "text": "Bank Details", "selected": False}],
        "buttons": [{"id": "b1", "text": "Submit application", "irreversible": True,
                     "kind": "submit"}],
        "errors": [],
    }


async def main_text(page, max_chars: int = 4000) -> str:
    """Readable article text without menus, at most max_chars."""
    # STUB: BRW-03
    return ("Kalpana Chawla was born on 17 March 1962 in Karnal, Haryana, India. "
            "She was the first woman of Indian origin to go to space.")[:max_chars]
