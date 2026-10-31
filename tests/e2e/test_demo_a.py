"""Task A, typed run over /ws/console with a scripted LLM."""
import pytest

from tests.e2e.harness import BlockedScenario, scenario_skip_reason
from tests.e2e.scenarios import scenario_a


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_demo_a_search_then_answer_contains_karnal():
    reason = scenario_skip_reason("A")
    if reason:
        pytest.skip(reason)
    try:
        evidence = await scenario_a()
    except BlockedScenario as exc:
        pytest.skip(str(exc))
    assert evidence
