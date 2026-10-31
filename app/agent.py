"""Autonomous agent loop (PRD Sections 7 and 12). Owner: M1."""
from app.session import Context, transition


async def handle_utterance(text: str, ctx: Context) -> None:
    """Entry point from main.py for every utterance from the Voice Console."""
    # STUB: CORE-10 / CORE-11 (command matcher first, then start or continue a task)
    await ctx.say(f"You said: {text}")


async def run_task(ctx: Context) -> None:
    """Run the current goal step by step, at most config.MAX_STEPS steps."""
    # STUB: CORE-10 (drive the loop with transition(), never by assigning session.state)
    return None


async def stop(ctx: Context) -> None:
    """Halt the agent loop within one step (hard rule 7)."""
    # STUB: CORE-10
    transition(ctx.session, "IDLE")
    await ctx.emit("state", name="IDLE")
    await ctx.say("Stopped.")
