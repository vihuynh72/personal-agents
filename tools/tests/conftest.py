import pytest

from tools.real import RealTools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests never reach the shared Cognee workspace; a test that wants Cognee fakes tools.cognee._http."""
    monkeypatch.delenv("COGNEE_URL", raising=False)
    monkeypatch.delenv("COGNEE_API_KEY", raising=False)
    RealTools._cognee_cache = None
    yield
    RealTools._cognee_cache = None
