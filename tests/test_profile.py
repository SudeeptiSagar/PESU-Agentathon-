"""CORE-07: encrypted profile. Uses a temp file and a low KDF cost; never touches ~/.voiceagent."""
import base64
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from app import config, profile
from app.profile import (DEMO_PROFILE, NoProfileError, ProfileCorruptError, ProfileError,
                         WrongPinError, load_profile, profile_exists, save_profile)


@pytest.fixture(autouse=True)
def tmp_profile(tmp_path, monkeypatch):
    path = tmp_path / "home" / ".voiceagent" / "profile.json"
    monkeypatch.setattr(config, "PROFILE_PATH", path)
    monkeypatch.setattr(profile, "KDF_ITERATIONS", 1_000)  # fast; the default is 600,000
    return path


def test_round_trip():
    assert not profile_exists()
    save_profile(DEMO_PROFILE, "2468")
    assert profile_exists()
    assert load_profile("2468") == DEMO_PROFILE


def test_wrong_pin_raises_wrong_pin_error():
    save_profile(DEMO_PROFILE, "2468")
    for bad in ("0000", "2469", "", "2468 ", "x" * 200):
        with pytest.raises(WrongPinError):
            load_profile(bad)
    with pytest.raises(WrongPinError):
        load_profile(None)  # type: ignore[arg-type]


def test_no_value_is_readable_on_disk(tmp_profile):
    save_profile(DEMO_PROFILE, "2468")
    raw = tmp_profile.read_text(encoding="utf-8")
    # The file holds only these fields, so no profile field can be stored in plain text...
    assert set(json.loads(raw)) == {"version", "kdf", "iterations", "salt", "token"}
    # ...and no value of a readable length appears in the text. Very short values such as "75" are
    # skipped: random base64 contains them by chance (about one run in nine), which says nothing.
    for key, value in DEMO_PROFILE.items():
        if len(value) >= 6:
            assert value not in raw, f"{key} is stored in plain text"
    assert "2468" not in raw  # the PIN is never stored


def test_sensitive_values_are_not_in_the_error_messages():
    save_profile(DEMO_PROFILE, "2468")
    with pytest.raises(WrongPinError) as err:
        load_profile("1111")
    text = str(err.value)
    assert not any(v in text for v in DEMO_PROFILE.values()) and "1111" not in text


def test_fresh_salt_each_save(tmp_profile):
    save_profile(DEMO_PROFILE, "2468")
    first = json.loads(tmp_profile.read_text())
    save_profile(DEMO_PROFILE, "2468")
    second = json.loads(tmp_profile.read_text())
    assert first["salt"] != second["salt"] and first["token"] != second["token"]
    assert len(base64.b64decode(first["salt"])) == 16


def test_overwrite_with_a_new_pin_invalidates_the_old_one():
    save_profile(DEMO_PROFILE, "2468")
    save_profile({"full_name": "Asha"}, "1357")
    assert load_profile("1357") == {"full_name": "Asha"}
    with pytest.raises(WrongPinError):
        load_profile("2468")


def test_partial_profile_is_fine():
    save_profile({"full_name": "Asha", "dob": "1990-01-02"}, "2468")
    assert load_profile("2468") == {"full_name": "Asha", "dob": "1990-01-02"}


@pytest.mark.parametrize("data,exc", [
    ({"favourite_colour": "blue"}, ValueError),     # unknown key = unknown placeholder
    ({"phone": 9876543210}, TypeError),              # values must be strings
    ({"full_name": None}, TypeError),
])
def test_bad_data_is_rejected_and_nothing_is_written(data, exc, tmp_profile):
    with pytest.raises(exc):
        save_profile(data, "2468")
    assert not tmp_profile.exists()


@pytest.mark.parametrize("pin", ["", "123", None, 1234])
def test_weak_or_invalid_pin_is_rejected(pin, tmp_profile):
    with pytest.raises(ValueError):
        save_profile(DEMO_PROFILE, pin)
    assert not tmp_profile.exists()


def test_profile_path_inside_the_repo_is_refused(monkeypatch):
    monkeypatch.setattr(config, "PROFILE_PATH", config.ROOT / "profile.json")
    with pytest.raises(ProfileError, match="outside the repository"):
        save_profile(DEMO_PROFILE, "2468")
    assert not (config.ROOT / "profile.json").exists()


def test_default_path_is_outside_the_repo():
    default = Path.home() / ".voiceagent" / "profile.json"
    assert config.ROOT.resolve() not in default.resolve().parents


def test_load_without_a_file():
    with pytest.raises(NoProfileError):
        load_profile("2468")


@pytest.mark.parametrize("content", [
    "not json", "[]", "{}", '{"version": 99}',
    json.dumps({"version": 1, "kdf": "pbkdf2-sha256", "iterations": 1000, "salt": "!!!", "token": "x"}),
    json.dumps({"version": 1, "kdf": "pbkdf2-sha256", "iterations": 10**12, "salt": "AAAA", "token": "x"}),
    json.dumps({"version": 1, "kdf": "pbkdf2-sha256", "iterations": 1000, "salt": "AAAA", "token": 5}),
])
def test_damaged_file_is_reported_as_corrupt_not_wrong_pin(tmp_profile, content):
    tmp_profile.parent.mkdir(parents=True)
    tmp_profile.write_text(content, encoding="utf-8")
    with pytest.raises(ProfileCorruptError):
        load_profile("2468")


def test_tampered_token_is_a_wrong_pin_not_a_crash(tmp_profile):
    save_profile(DEMO_PROFILE, "2468")
    doc = json.loads(tmp_profile.read_text())
    doc["token"] = doc["token"][:-4] + "AAAA"
    tmp_profile.write_text(json.dumps(doc))
    with pytest.raises(WrongPinError):
        load_profile("2468")


def test_atomic_write_leaves_no_temp_files(tmp_profile):
    save_profile(DEMO_PROFILE, "2468")
    assert [p.name for p in tmp_profile.parent.iterdir()] == ["profile.json"]


def test_failed_write_keeps_the_old_profile_and_cleans_up(tmp_profile, monkeypatch):
    save_profile({"full_name": "Asha"}, "2468")

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(profile.os, "replace", boom)
    with pytest.raises(OSError):
        save_profile({"full_name": "Someone Else"}, "2468")
    assert load_profile("2468") == {"full_name": "Asha"}
    assert [p.name for p in tmp_profile.parent.iterdir()] == ["profile.json"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_file_is_owner_only(tmp_profile):
    save_profile(DEMO_PROFILE, "2468")
    assert stat.S_IMODE(tmp_profile.stat().st_mode) == 0o600


def test_placeholder_keys_cover_the_prd_fields():
    assert set(profile.PLACEHOLDER_KEYS) == set(DEMO_PROFILE)
    assert set(profile.ENCRYPTED_FIELDS) <= set(config.SENSITIVE_KEYS)
    assert len(set(profile.PLACEHOLDER_KEYS)) == len(profile.PLACEHOLDER_KEYS)


def test_default_kdf_cost_is_at_least_the_owasp_floor():
    importlib_spec = importlib.util.find_spec("app.profile")
    assert importlib_spec is not None
    src = Path(importlib_spec.origin).read_text(encoding="utf-8")
    assert "KDF_ITERATIONS = 600_000" in src  # the fixture lowers it only for tests


def test_demo_profile_script(tmp_profile, capsys, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "make_demo_profile", Path(__file__).resolve().parent.parent / "scripts" / "make_demo_profile.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    monkeypatch.setattr(sys, "argv", ["x", "--pin", "2468"])
    assert mod.main() == 0 and load_profile("2468") == DEMO_PROFILE
    assert mod.main() == 1                                  # refuses to overwrite
    assert "already exists" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["x", "--pin", "1357", "--force"])
    assert mod.main() == 0 and load_profile("1357") == DEMO_PROFILE
