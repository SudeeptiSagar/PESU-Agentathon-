"""JEV-06: the audit log writes compact JSONL without sensitive values."""

import json
import logging
import threading
from datetime import datetime, timezone

import pytest

from app import audit, config


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    """Point the module at a throwaway file for every test."""
    path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit, "LOG_PATH", path)
    return path


def _text(path):
    return path.read_text(encoding="utf-8")


def _events(path):
    return [json.loads(line) for line in _text(path).splitlines() if line.strip()]


def test_nested_sensitive_fields_are_dropped_and_pin_code_survives(log_path):
    audit.log_event(
        "fill_field",
        action="fill_field",
        aadhaar="1234 5678 9012",
        bank_account="123456789012",
        ifsc="HDFC0001234",
        pin="4821",
        pin_code="560001",
        profile={
            "aadhaar_number": "1234 5678 9012",
            "bank_account": "123456789012",
            "ifsc_code": "HDFC0001234",
            "pin_value": "4821",
            "pin_code": "560001",
        },
        field_list=[{"pin_code": "560001"}, {"pin": "4821"}],
    )

    text = _text(log_path)
    event = _events(log_path)[0]

    # The postal code is ordinary data and stays readable and unmasked.
    assert event["pin_code"] == "560001"
    assert event["action"] == "fill_field"
    assert event["profile"] == {"pin_code": "560001"}
    assert event["field_list"] == [{"pin_code": "560001"}, {}]
    assert "560001" in text

    # No raw sensitive value reaches the file.
    for raw in ("1234 5678 9012", "123456789012", "HDFC0001234", "4821"):
        assert raw not in text

    # No sensitive key name reaches the file either.
    for name in ("aadhaar", "bank_account", "ifsc", "aadhaar_number", "ifsc_code", "pin_value"):
        assert name not in text
    assert '"pin"' not in text

    assert datetime.fromisoformat(event["ts"]).tzinfo is not None


def test_generic_values_are_scrubbed_but_short_numbers_and_urls_survive(log_path):
    audit.log_event(
        "probe",
        reference="account 123456789012",
        card="4111 1111 1111 1111",
        card_mixed="5500-0000 0000-4444",
        note="pin_code 560001, port 8080, field f3",
        port=8080,
        field_id="f3",
        number=4821,
        when="2026-10-31T18:30:00+00:00",
        url="http://localhost:8000/portal/apply.html?q=560001",
    )

    text = _text(log_path)
    event = _events(log_path)[0]

    # A 12+ digit run under a generic key is masked to its last four digits.
    assert "123456789012" not in text
    assert event["reference"] == "account ********9012"
    assert event["card"] == "**** **** **** 1111"
    assert event["card_mixed"] == "****-**** ****-4444"

    # Ordinary short numbers, field ids, timestamps and URLs are untouched.
    assert event["note"] == "pin_code 560001, port 8080, field f3"
    assert event["port"] == 8080
    assert event["field_id"] == "f3"
    assert event["number"] == 4821
    assert event["when"] == "2026-10-31T18:30:00+00:00"
    assert event["url"] == "http://localhost:8000/portal/apply.html?q=560001"


def test_api_key_fields_are_dropped_and_the_jev_key_value_is_redacted(log_path, monkeypatch):
    monkeypatch.setattr(config, "JEV_API_KEY", "jev-live-abc123")

    audit.log_event(
        "gate",
        action="check",
        api_key="plain-api-key",
        jev_api_key="jev-live-abc123",
        typesafe_api_key="ts-key-999",
        custom_api_key="custom-secret-xyz",
        note="calling with jev-live-abc123",
        nested={
            "access_token": "token-value-xyz",
            "password": "password-value-xyz",
            "secret": "secret-value-xyz",
            "otp": "otp-value-xyz",
            "cvv": "cvv-value-xyz",
        },
    )

    text = _text(log_path)
    event = _events(log_path)[0]

    assert event["note"] == "calling with [redacted]"
    assert event["nested"] == {}
    assert event["action"] == "check"
    for secret in (
        "plain-api-key",
        "jev-live-abc123",
        "ts-key-999",
        "custom-secret-xyz",
        "token-value-xyz",
        "password-value-xyz",
        "secret-value-xyz",
        "otp-value-xyz",
        "cvv-value-xyz",
    ):
        assert secret not in text
    for name in ("api_key", "jev_api_key", "typesafe_api_key", "custom_api_key",
                 "access_token", "password", "secret", "otp", "cvv"):
        assert f'"{name}"' not in text


def test_two_threads_write_forty_valid_json_lines(log_path):
    def worker(worker_id):
        for step in range(20):
            audit.log_event("step", worker=worker_id, step=step, note="x" * 40)

    threads = [threading.Thread(target=worker, args=(worker_id,)) for worker_id in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    events = _events(log_path)  # json.loads would raise on any torn or invalid line
    assert len(events) == 40
    assert all(event["kind"] == "step" for event in events)
    assert {(event["worker"], event["step"]) for event in events} == {
        (worker_id, step) for worker_id in (1, 2) for step in range(20)
    }


def test_parent_directories_are_created(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "deeper" / "audit.jsonl"
    monkeypatch.setattr(audit, "LOG_PATH", path)

    audit.log_event("startup")

    assert path.is_file()
    assert len(_events(path)) == 1


def test_write_failure_logs_a_warning_and_does_not_raise(tmp_path, monkeypatch, caplog):
    # A directory cannot be opened for append: this stands in for a full disk.
    monkeypatch.setattr(audit, "LOG_PATH", tmp_path)

    with caplog.at_level(logging.WARNING, logger="app.audit"):
        audit.log_event("boom")  # must not raise

    assert any("could not write event" in record.message for record in caplog.records)


def test_other_types_are_stringified_and_scrubbed(log_path):
    class Widget:
        def __str__(self):
            return "widget-1"

    audit.log_event(
        "weird",
        widget=Widget(),
        when=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
        pair=("a", 1),
        tags={"b", "a"},
        nothing=None,
    )

    event = _events(log_path)[0]
    assert event["widget"] == "widget-1"
    assert event["when"].startswith("2026-10-31 12:00:00")
    assert event["pair"] == ["a", 1]
    assert event["tags"] == ["a", "b"]
    assert event["nothing"] is None


def test_caller_cannot_override_the_logger_timestamp(log_path):
    audit.log_event("real", ts="fake")

    event = _events(log_path)[0]
    assert event["kind"] == "real"
    assert event["ts"] != "fake"
    assert datetime.fromisoformat(event["ts"]).tzinfo is not None
