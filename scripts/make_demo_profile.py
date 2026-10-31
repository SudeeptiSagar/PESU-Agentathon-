"""Save a fictional demo profile so the agent can be tried before onboarding (UI-07) exists.

    python scripts/make_demo_profile.py --pin 1234
    python scripts/make_demo_profile.py --pin 1234 --force     # replace an existing profile

Writes to config.PROFILE_PATH (default ~/.voiceagent/profile.json, outside the repo). The data
is made up (app.profile.DEMO_PROFILE). Never run this over a profile that holds real data
without --force, and it refuses to by default. Owner: M1.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, profile  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pin", required=True, help=f"PIN to lock the profile, {profile.MIN_PIN_LENGTH}+ characters")
    ap.add_argument("--force", action="store_true", help="overwrite an existing profile")
    args = ap.parse_args()

    if profile.profile_exists() and not args.force:
        print(f"A profile already exists at {config.PROFILE_PATH}. Use --force to replace it.")
        return 1
    profile.save_profile(profile.DEMO_PROFILE, args.pin)
    profile.load_profile(args.pin)  # prove it unlocks
    print(f"Saved the demo profile (fictional data) to {config.PROFILE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
