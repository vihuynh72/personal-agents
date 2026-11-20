"""The calendar service's API for web/: availability per guest and slot, and connect -> Google -> back to web/."""
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from tools import calendar_demo as demo
from tools import cognee as cognee_mod
from tools import google_calendar as gc
from tools.availability import AIRBYTE, SIMULATED, record_text, replace_record
from tools.cognee import Cognee
from tools.tests.test_cognee import FakeCognee

WINDOW = ("2026-11-14T00:00:00Z", "2026-12-31T00:00:00Z")
SAT_BUSY = [{"start": "2026-11-28T09:00:00-08:00", "end": "2026-11-28T23:30:00-08:00"}]


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNEE_URL", "https://cognee.test")
    monkeypatch.setenv("COGNEE_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8001/oauth/google/callback")
    monkeypatch.setattr(cognee_mod, "_http", FakeCognee())
    monkeypatch.setattr(gc, "TOKENS", tmp_path / "tokens")
    demo._return_to.clear()
    return TestClient(demo.app)  # no `with`: the background sync loop is not started in tests


def test_availability_per_guest_and_slot(client, monkeypatch):
    c = Cognee()
    replace_record(c, "g3", record_text("g3", "Jamie", SAT_BUSY, WINDOW, SIMULATED, "t"))
    r = client.get("/api/availability", params={"ids": "g3,g6", "slots": "sat7,sun6"})
    assert r.status_code == 200
    people = r.json()["people"]
    assert people["g3"]["sat7"] == {"status": "busy", "source": SIMULATED, "synced_at": "t"}
    assert people["g3"]["sun6"]["status"] == "free"
    assert people["g6"]["sat7"] == {"status": "pending", "source": None, "synced_at": None}  # no record: never free


def test_real_calendar_is_labelled_airbyte(client, monkeypatch):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    replace_record(Cognee(), "g1", record_text("g1", "Ketki", [], WINDOW, AIRBYTE, now))
    a = client.get("/api/availability", params={"ids": "g1"}).json()["people"]["g1"]
    assert set(a) == {"fri730", "sat7", "sun6"}
    assert all(v["status"] == "free" and v["source"] == AIRBYTE for v in a.values())


def test_unknown_slot_and_unsafe_id_are_rejected(client):
    assert client.get("/api/availability", params={"ids": "g1", "slots": "mon9"}).status_code == 400
    with pytest.raises(ValueError):
        client.get("/api/availability", params={"ids": "../x"})


def test_cors_allows_the_front_end_only(client):
    ok = client.get("/api/availability", params={"ids": "g1"}, headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    other = client.get("/api/availability", params={"ids": "g1"}, headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in other.headers


def test_connect_returns_to_the_front_end(client, monkeypatch):
    r = client.get("/connect/g1", params={"return_to": "http://localhost:5173/"}, follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].startswith(gc.AUTH)
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(r.headers["location"]).query))["state"]
    back = client.get("/oauth/google/callback", params={"state": state, "error": "access_denied"},
                      follow_redirects=False)
    assert back.headers["location"] == "http://localhost:5173/?calendar=declined&id=g1"


def test_connect_refuses_to_send_people_elsewhere(client):
    r = client.get("/connect/g1", params={"return_to": "https://evil.test/"}, follow_redirects=False)
    assert r.status_code == 400
