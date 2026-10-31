"""Encrypted local user profile (PRD Sections 10 and 11). Owner: M1.

Fernet with a PBKDF2 key derived from the PIN and a random salt. The file lives at
config.PROFILE_PATH, outside the repo. Real values never reach the LLM (hard rule 1).
"""

PLAIN_FIELDS = ("full_name", "dob", "gender", "address", "city", "state", "pin_code",
                "phone", "email", "annual_income", "category", "disability_percent")
ENCRYPTED_FIELDS = ("aadhaar", "bank_account", "ifsc")

# Fictional sample data used by the stub only.
_SAMPLE = {
    "full_name": "Ramesh Kumar", "dob": "1980-03-04", "gender": "male",
    "address": "12 MG Road", "city": "Bengaluru", "state": "Karnataka", "pin_code": "560001",
    "phone": "9876543210", "email": "ramesh@example.com", "annual_income": "120000",
    "category": "General", "disability_percent": "75",
    "aadhaar": "000011112222", "bank_account": "000000001234", "ifsc": "TEST0000001",
}


class WrongPinError(Exception):
    """The PIN did not decrypt the profile."""


def profile_exists() -> bool:
    """True if an encrypted profile file exists."""
    # STUB: CORE-07
    return True


def save_profile(data: dict, pin: str) -> None:
    """Encrypt and write the profile. Sensitive fields get field-level encryption."""
    # STUB: CORE-07
    return None


def load_profile(pin: str) -> dict:
    """Decrypt and return the profile. Raises WrongPinError on a wrong PIN."""
    # STUB: CORE-07
    if pin == "0000":
        raise WrongPinError("wrong PIN")
    return dict(_SAMPLE)
