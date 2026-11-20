import pytest


@pytest.fixture(autouse=True)
def _immediate_followup(monkeypatch):
    """Production waits until 24 hours after the estimated arrival; tests ask for the follow-up at once."""
    monkeypatch.setenv("FEEDBACK_DELAY_SECONDS", "0")
