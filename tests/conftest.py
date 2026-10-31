"""Test defaults. Owner: M1.

The backend shares one Context for the whole app (app.main.get_hub). Without this, a test that sends an
utterance over the WebSocket would start a REAL browser window, would try to unlock the REAL profile in
~/.voiceagent, and tests would leak state into each other. So every test gets a fresh hub, no browser factory
("the browser is not ready"), an empty profile location and silent onboarding. Tests that want any of these set
them themselves. The end-to-end tests (tests/e2e) are the exception: they run the real backend with a real browser
and their own fake profile, so they only get a fresh hub.
"""
import pytest


@pytest.fixture(autouse=True)
def isolated_backend(request, monkeypatch, tmp_path_factory):
    from app import config, main

    monkeypatch.setattr(main.app.state, "hub", None, raising=False)
    if "e2e" not in request.node.path.parts:
        async def silent(ctx):
            return None

        monkeypatch.setattr(main.app.state, "browser_factory", None, raising=False)
        # An empty, private location: profile_exists() is honestly False and the real ~/.voiceagent is never touched.
        monkeypatch.setattr(config, "PROFILE_PATH", tmp_path_factory.mktemp("no_profile") / "profile.json")
        monkeypatch.setattr(main.onboarding, "run_unlock", silent)
        monkeypatch.setattr(main.onboarding, "run_onboarding", silent)
    yield
