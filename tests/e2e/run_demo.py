"""Run the three typed demo scenarios and print a status line for each.

Usage, from the repository root:

    python -m tests.e2e.run_demo

Exit code 0 only when A, B and C all PASS. BLOCKED is used while a required ticket is
still missing (for example CORE-12 for demo B); FAIL means the scenario ran and a safety
or flow assertion failed.
"""
from __future__ import annotations

import asyncio
import sys

from tests.e2e.harness import BlockedScenario, redact
from tests.e2e.scenarios import SCENARIOS


async def _run(scenario: str) -> tuple[str, str]:
    try:
        evidence = await SCENARIOS[scenario]()
    except BlockedScenario as exc:
        return "BLOCKED", redact(str(exc))
    except Exception as exc:  # noqa: BLE001 - CLI reports the real failure
        return "FAIL", redact(f"{type(exc).__name__}: {exc}")
    return "PASS", redact(evidence)


def main() -> int:
    results: dict[str, str] = {}
    details: dict[str, str] = {}
    for scenario in ("A", "B", "C"):
        status, detail = asyncio.run(_run(scenario))
        results[scenario] = status
        details[scenario] = detail
        print(f"{scenario}: {status}")
        for line in detail.splitlines():
            print(f"  {line}")

    if all(status == "PASS" for status in results.values()):
        final = "PASS"
    elif any(status == "FAIL" for status in results.values()):
        final = "FAIL"
    else:
        final = "BLOCKED"
    print(f"RESULT: {final}")
    return 0 if final == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
