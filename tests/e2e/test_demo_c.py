"""Task C, typed run over /ws/console: held Place order, then payment hand-off."""
import pytest

from tests.e2e.harness import BlockedScenario, scenario_skip_reason
from tests.e2e.scenarios import scenario_c


@pytest.mark.asyncio
async def test_demo_c_no_order_before_confirm_then_payment_handoff():
    reason = scenario_skip_reason("C")
    if reason:
        pytest.skip(reason)
    try:
        evidence = await scenario_c()
    except BlockedScenario as exc:
        pytest.skip(str(exc))
    assert evidence
