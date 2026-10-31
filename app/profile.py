"""Encrypted local user profile (PRD Sections 10 and 11). Owner: M1.

The whole profile is one Fernet token, encrypted with a key derived from the user's PIN
(PBKDF2-HMAC-SHA256, random salt, stored beside the token). That is stronger than the PRD's
minimum, which encrypted only aadhaar, bank_account and ifsc: no field is readable on disk.
The file lives at config.PROFILE_PATH, outside the repo. The PIN is never stored or logged.
Real values never reach the LLM (hard rule 1); it sees placeholder names only.

Limit worth knowing: the PIN is the only secret. A 4-digit PIN can be guessed offline in
minutes by someone who copies the file, so the file's location and permissions still matter.
"""
import base64
import json
import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app import config

PLAIN_FIELDS = ("full_name", "dob", "gender", "address", "city", "state", "pin_code",
                "phone", "email", "annual_income", "category", "disability_percent")
ENCRYPTED_FIELDS = ("aadhaar", "bank_account", "ifsc")
# The only keys a profile may hold. They are also the placeholder names ({dob}, {phone}, ...).
PLACEHOLDER_KEYS = PLAIN_FIELDS + ENCRYPTED_FIELDS

KDF_ITERATIONS = 600_000  # about 0.1 s on a laptop; stored in the file so it can be raised later
MIN_PIN_LENGTH = 4
_FORMAT_VERSION = 1

# Fictional data for tests and scripts/make_demo_profile.py. Never loaded automatically.
DEMO_PROFILE = {
    "full_name": "Ramesh Kumar", "dob": "1980-03-04", "gender": "male",
    "address": "12 MG Road", "city": "Bengaluru", "state": "Karnataka", "pin_code": "560001",
    "phone": "9876543210", "email": "ramesh@example.com", "annual_income": "120000",
    "category": "General", "disability_percent": "75",
    "aadhaar": "000011112222", "bank_account": "000000001234", "ifsc": "TEST0000001",
}


class ProfileError(Exception):
    """Base class for profile problems. Messages never contain profile values or the PIN."""


class WrongPinError(ProfileError):
    """The PIN did not decrypt the profile."""


class NoProfileError(ProfileError):
    """There is no profile file yet."""


class ProfileCorruptError(ProfileError):
    """The profile file is unreadable or from an unknown version."""


def _path() -> Path:
    return Path(config.PROFILE_PATH)


def _key(pin: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return base64.urlsafe_b64encode(kdf.derive(pin.encode("utf-8")))


def _ensure_outside_repo(path: Path) -> None:
    root = config.ROOT.resolve()
    target = path.resolve()
    if target == root or root in target.parents:
        raise ProfileError("the profile file must be stored outside the repository")


def profile_exists() -> bool:
    """True if an encrypted profile file exists."""
    return _path().is_file()


def save_profile(data: dict, pin: str) -> None:
    """Encrypt the whole profile with a key derived from `pin` and write it atomically.

    `data` may only hold keys from PLACEHOLDER_KEYS, with string values. A fresh random salt is
    used on every save. Raises ValueError/TypeError for bad input, ProfileError if the path is
    inside the repo.
    """
    if not isinstance(pin, str) or len(pin) < MIN_PIN_LENGTH:
        raise ValueError(f"the PIN must be at least {MIN_PIN_LENGTH} characters")
    unknown = sorted(set(data) - set(PLACEHOLDER_KEYS))
    if unknown:
        raise ValueError(f"unknown profile fields: {', '.join(unknown)}")
    if not all(isinstance(v, str) for v in data.values()):
        raise TypeError("profile values must be strings")

    path = _path()
    _ensure_outside_repo(path)
    salt = os.urandom(16)
    token = Fernet(_key(pin, salt, KDF_ITERATIONS)).encrypt(json.dumps(data).encode("utf-8"))
    doc = {"version": _FORMAT_VERSION, "kdf": "pbkdf2-sha256", "iterations": KDF_ITERATIONS,
           "salt": base64.b64encode(salt).decode("ascii"), "token": token.decode("ascii")}

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".profile-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        try:
            os.chmod(tmp, 0o600)  # owner only; limited effect on Windows
        except OSError:
            pass
        os.replace(tmp, path)  # a crash mid-write never leaves a half-written profile
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_profile(pin: str) -> dict:
    """Decrypt and return the profile. Raises WrongPinError on a wrong PIN."""
    path = _path()
    if not path.is_file():
        raise NoProfileError("no profile has been saved yet")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc["version"] != _FORMAT_VERSION or doc["kdf"] != "pbkdf2-sha256":
            raise ProfileCorruptError("unknown profile format")
        salt = base64.b64decode(doc["salt"], validate=True)
        iterations = int(doc["iterations"])
        if not 1_000 <= iterations <= 10_000_000:  # a tampered file must not hang the unlock
            raise ProfileCorruptError("unreasonable key-derivation settings")
        token = doc["token"].encode("ascii")
    except ProfileCorruptError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise ProfileCorruptError("the profile file is damaged") from None
    if not isinstance(pin, str) or not pin:
        raise WrongPinError("wrong PIN")
    try:
        raw = Fernet(_key(pin, salt, iterations)).decrypt(token)
    except InvalidToken:
        raise WrongPinError("wrong PIN") from None
    try:
        data = json.loads(raw)
    except ValueError:
        raise ProfileCorruptError("the profile contents are damaged") from None
    if not isinstance(data, dict):
        raise ProfileCorruptError("the profile contents are damaged")
    return data
