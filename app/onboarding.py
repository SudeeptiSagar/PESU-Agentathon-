"""First-run onboarding and PIN unlock in the Voice Console. Owner: M2 (Vishal).

CORE-01 contract stubs; replace the bodies, keep the signatures.
"""
from app import profile


async def run_onboarding(ctx) -> None:
    """Ask profile questions one at a time, confirm each, then call profile.save_profile."""
    # STUB: UI-07
    await ctx.say("Onboarding is not ready yet.")


async def run_unlock(ctx) -> None:
    """Ask for the PIN and call profile.load_profile into ctx.session.profile."""
    # STUB: UI-07
    ctx.session.profile = profile.load_profile("1234")
    await ctx.say("Profile unlocked.")
