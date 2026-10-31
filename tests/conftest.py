"""Test defaults. Owner: M1.

The backend shares one Context for the whole app (app.main.get_hub). Without this, a test that sends an
utterance over the WebSocket would start a REAL browser window, and tests would leak state into each other.
So every test gets a fresh hub and no browser factory ("the browser is not ready"). Tests that want a browser
set app.state.browser_factory themselves. The end-to-end tests (tests/e2e) are the exception: they run the
real backend with a real browser, so they only get a fresh hub.
"""
import pytest


@pytest.fixture(autouse=True)
def isolated_backend(request, monkeypatch):
    from app.main import app

    monkeypatch.setattr(app.state, "hub", None, raising=False)
    if "e2e" not in request.node.path.parts:
        monkeypatch.setattr(app.state, "browser_factory", None, raising=False)
    yield
