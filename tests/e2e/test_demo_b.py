"""Task B, typed run over /ws/console with a scripted LLM and the planted PIN trap."""
import pytest

from tests.e2e.harness import BlockedScenario, scenario_skip_reason
from tests.e2e.scenarios import scenario_b


@pytest.mark.asyncio
async def test_demo_b_verifier_human_check_readback_confirm():
    reason = scenario_skip_reason("B")
    if reason:
        pytest.skip(reason)
    try:
        evidence = await scenario_b()
    except BlockedScenario as exc:
        pytest.skip(str(exc))
    assert evidence
