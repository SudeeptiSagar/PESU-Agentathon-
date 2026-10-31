"""Make the real-app e2e suite opt-in without breaking an explicit path.

- ``pytest -q`` skips the e2e tests, so the default suite stays fast and quiet.
- ``pytest -m e2e`` runs them.
- ``pytest tests/e2e`` runs them too, because the caller named the path.

The marker itself is registered in ``pytest.ini`` and applied in each e2e test
module with ``pytestmark = pytest.mark.e2e``.
"""
import pytest


def pytest_collection_modifyitems(config, items):
    marker = (config.getoption("-m") or "").strip()
    explicit_path = any(
        "e2e" in str(path).replace("\\", "/") for path in config.args
    )
    if marker == "e2e" or explicit_path:
        return
    skip = pytest.mark.skip(
        reason="e2e tests are opt-in; run `pytest -m e2e` or pass tests/e2e"
    )
    for item in items:
        if item.get_closest_marker("e2e"):
            item.add_marker(skip)
