"""JEV-03: read-back and pending-action description tests (no Playwright)."""
import pytest

from app.readback import CONFIRM_INSTRUCTION, build_readback, describe_pending
from app.session import Session

FINAL = "Say confirm to go ahead, or say change followed by the field name."


def _session(expected: dict) -> Session:
    return Session(expected=expected)


def _field(label: str, value, *, field_type: str = "text",
           source: str = "profile:full_name") -> dict:
    return {"label": label, "selector": "#field", "value": value,
            "type": field_type, "source": source}


# ------------------------------------------------------------------ read-back

def test_actual_value_overrides_expected():
    session = _session({"full_name": _field("Full name", "Ramesh Kumar")})
    chunks = build_readback(session, {"full_name": "Ramesh K."})
    assert chunks == ["Full name: Ramesh K.", FINAL]


def test_actual_value_accepts_value_and_actual_shapes():
    session = _session({"full_name": _field("Full name", "Ramesh Kumar")})
    assert build_readback(session, {"full_name": {"value": "Ramesh V."}})[0] == "Full name: Ramesh V."
    assert build_readback(session, {"full_name": {"actual": "Ramesh A."}})[0] == "Full name: Ramesh A."


def test_expected_value_is_the_fallback():
    session = _session({"full_name": _field("Full name", "Ramesh Kumar")})
    assert build_readback(session, {})[0] == "Full name: Ramesh Kumar."
    assert build_readback(session, {"full_name": None})[0] == "Full name: Ramesh Kumar."


def test_only_expected_fields_in_insertion_order():
    session = _session({
        "full_name": _field("Full name", "Ramesh Kumar"),
        "city": _field("City", "Bengaluru", source="profile:city"),
    })
    chunks = build_readback(session, {"city": "Mysuru", "unknown": "ignored"})
    assert chunks == ["Full name: Ramesh Kumar.", "City: Mysuru.", FINAL]


def test_final_instruction_is_exact_and_last():
    chunks = build_readback(_session({}), {})
    assert chunks == [FINAL]
    assert chunks[-1] == "Say confirm to go ahead, or say change followed by the field name."
    assert CONFIRM_INSTRUCTION == FINAL


def test_phone_digits_are_separated():
    session = _session({"phone": _field("Phone", "9876543210", field_type="tel",
                                        source="profile:phone")})
    assert build_readback(session, {"phone": "+91 98765 43210"})[0] == \
        "Phone: 9 1 9 8 7 6 5 4 3 2 1 0."


def test_date_is_spoken_naturally():
    session = _session({"dob": _field("Date of birth", "1980-03-04", field_type="date",
                                      source="profile:dob")})
    chunks = build_readback(session, {"dob": "1980-03-04"})
    assert chunks[0] == "Date of birth: 4 March 1980."
    assert build_readback(session, {"dob": "4 March 1980"})[0] == "Date of birth: 4 March 1980."


def test_aadhaar_masked_to_last_four():
    raw = "1234 5678 9012"
    session = _session({"aadhaar": _field("Aadhaar", raw, source="profile:aadhaar")})
    chunks = build_readback(session, {"aadhaar": raw})
    assert chunks[0] == "Aadhaar: ending 9 0 1 2."
    assert raw not in " ".join(chunks)
    assert "123456789012" not in " ".join(chunks).replace(" ", "")


def test_bank_account_masked_to_last_four():
    raw = "123456789012"
    session = _session({"bank_account": _field("Bank account", raw,
                                               source="profile:bank_account")})
    chunks = build_readback(session, {"bank_account": raw})
    assert chunks[0] == "Bank account: ending 9 0 1 2."
    assert raw not in " ".join(chunks)


def test_ifsc_masked_to_last_four():
    raw = "SBIN0001234"
    session = _session({"ifsc": _field("IFSC", raw, source="profile:ifsc")})
    chunks = build_readback(session, {"ifsc": raw})
    assert chunks[0] == "IFSC: ending 1 2 3 4."
    assert raw not in " ".join(chunks)


def test_unlock_pin_masked_to_last_four():
    raw = "9876"
    session = _session({"pin": _field("Unlock PIN", raw, field_type="password",
                                      source="profile:pin")})
    chunks = build_readback(session, {"pin": raw})
    assert chunks[0] == "Unlock PIN: ending 9 8 7 6."
    assert raw not in " ".join(chunks)


def test_pin_code_is_postal_not_sensitive():
    session = _session({"pin_code": _field("PIN code", "560001",
                                           source="profile:pin_code")})
    chunks = build_readback(session, {"pin_code": "560001"})
    assert chunks[0] == "PIN code: 5 6 0 0 0 1."
    assert "ending" not in chunks[0]


def test_pin_code_trap_speaks_every_digit_and_never_masks():
    session = _session({"pin_code": _field("PIN code", "560001",
                                           source="profile:pin_code")})
    chunk = build_readback(session, {"pin_code": "560 001"})[0]
    assert chunk == "PIN code: 5 6 0 0 0 1."
    assert "ending" not in chunk
    assert "560001" not in chunk


def test_empty_value_is_spoken_as_empty():
    session = _session({"full_name": _field("Full name", "Ramesh Kumar")})
    assert build_readback(session, {"full_name": ""})[0] == "Full name is empty."
    assert build_readback(session, {"full_name": {"value": ""}})[0] == "Full name is empty."


def test_empty_sensitive_value_is_not_spoken_as_none():
    session = _session({"aadhaar": _field("Aadhaar number", "1234 5678 9012",
                                           source="profile:aadhaar")})
    chunk = build_readback(session, {"aadhaar": ""})[0]
    assert chunk == "Aadhaar number is empty."
    assert "None" not in chunk
    assert "ending" not in chunk


def test_whitespace_is_collapsed():
    session = _session({"address": _field("Address", "12 MG Road",
                                          source="profile:address")})
    chunk = build_readback(session, {"address": "  12 MG Road,\n\tBengaluru  "})[0]
    assert chunk == "Address: 12 MG Road, Bengaluru."


def test_no_sensitive_value_ever_appears_raw():
    expected = {
        "aadhaar": _field("Aadhaar", "1234 5678 9012", source="profile:aadhaar"),
        "bank_account": _field("Bank account", "123456789012",
                               source="profile:bank_account"),
        "ifsc": _field("IFSC", "SBIN0001234", source="profile:ifsc"),
        "pin": _field("Unlock PIN", "9876", field_type="password", source="profile:pin"),
        "pin_code": _field("PIN code", "560001", source="profile:pin_code"),
    }
    actual = {
        "aadhaar": "1234 5678 9012",
        "bank_account": "123456789012",
        "ifsc": "SBIN0001234",
        "pin": "9876",
        "pin_code": "560001",
    }
    chunks = build_readback(_session(expected), actual)
    joined = " ".join(chunks)
    compact = joined.replace(" ", "")
    for raw in ("1234 5678 9012", "123456789012", "SBIN0001234", "9876"):
        assert raw not in joined, raw
    # Long values must not survive even with the spoken spaces removed; the PIN is
    # spoken as "9 8 7 6", so only the contiguous form can leak.
    for raw in ("123456789012", "SBIN0001234"):
        assert raw not in compact, raw
    assert "PIN code: 5 6 0 0 0 1." in chunks
    assert chunks[-1] == FINAL


# ----------------------------------------------------------- pending action

def test_describe_pending_names_action_site_and_total():
    session = Session(pending_action={
        "element_id": "b4", "label": "Place order", "kind": "order",
        "url": "http://localhost:8000/web/shop.html", "domain": "localhost",
        "site": "demo shop", "total": 249,
    })
    assert describe_pending(session) == \
        "I'm about to press Place order on demo shop. Total 249 rupees."


def test_describe_pending_prettifies_site_id():
    session = Session(pending_action={
        "label": "Place order", "site_id": "demo_shop", "total": 249.0,
    })
    assert describe_pending(session) == \
        "I'm about to press Place order on demo shop. Total 249 rupees."


def test_describe_pending_prefers_site_over_site_id():
    session = Session(pending_action={
        "label": "Place order", "site": "Demo Shop", "site_id": "demo_portal",
    })
    assert describe_pending(session) == "I'm about to press Place order on Demo Shop."


def test_describe_pending_maps_known_domain_from_sites_json():
    session = Session(pending_action={"label": "Submit application", "domain": "localhost"})
    assert describe_pending(session) == \
        "I'm about to press Submit application on demo portal."


def test_describe_pending_uses_url_path_when_localhost_is_ambiguous():
    # Both demo sites share the localhost domain. The URL path must decide.
    shop = Session(pending_action={
        "label": "Place order", "domain": "localhost",
        "url": "http://localhost:8000/web/checkout.html", "total": 249,
    })
    assert describe_pending(shop) == \
        "I'm about to press Place order on demo shop. Total 249 rupees."

    portal = Session(pending_action={
        "label": "Submit application", "domain": "localhost",
        "url": "http://localhost:8000/portal/apply.html",
    })
    assert describe_pending(portal) == \
        "I'm about to press Submit application on demo portal."


def test_describe_pending_maps_wikipedia_domain():
    session = Session(pending_action={"label": "Search", "domain": "en.wikipedia.org"})
    assert describe_pending(session) == "I'm about to press Search on wikipedia."


def test_describe_pending_falls_back_to_unknown_domain():
    session = Session(pending_action={"label": "Apply", "domain": "example.org"})
    assert describe_pending(session) == "I'm about to press Apply on example.org."


def test_describe_pending_without_total_omits_the_clause():
    session = Session(pending_action={"label": "Submit application", "site": "demo portal"})
    description = describe_pending(session)
    assert description == "I'm about to press Submit application on demo portal."
    assert "Total" not in description


def test_describe_pending_uses_kind_when_label_is_missing():
    session = Session(pending_action={"kind": "submit", "site": "demo portal"})
    assert describe_pending(session) == "I'm about to press Submit on demo portal."


def test_describe_pending_uses_amount_and_total_text():
    numeric = Session(pending_action={"label": "Pay", "site": "demo shop", "amount": 99})
    assert describe_pending(numeric) == \
        "I'm about to press Pay on demo shop. Total 99 rupees."

    text = Session(pending_action={"label": "Place order", "site": "demo shop",
                                   "total_text": "₹249.00"})
    assert describe_pending(text) == \
        "I'm about to press Place order on demo shop. Total ₹249.00."


@pytest.mark.parametrize("total, spoken", [
    (249, "249"),
    (249.0, "249"),
    (249.5, "249.50"),
    ("249.00", "249"),
    (1234, "1,234"),
    (100000, "1,00,000"),
    (1234567, "12,34,567"),
    (0, "0"),
])
def test_describe_pending_formats_indian_numeric_totals(total, spoken):
    session = Session(pending_action={"label": "Place order", "site": "demo shop",
                                      "total": total})
    assert describe_pending(session) == \
        f"I'm about to press Place order on demo shop. Total {spoken} rupees."


def test_describe_pending_without_a_pending_action():
    assert describe_pending(Session()) == "There is no action waiting for confirmation."
