import json
import urllib.parse

import pytest

from tools import google_calendar as gc


class FakeGoogle:
    def __init__(self):
        self.granted = " ".join(gc.SCOPES)

    def __call__(self, method, url, headers, body, timeout=20):
        assert url == gc.TOKEN
        form = dict(urllib.parse.parse_qsl(body.decode()))
        assert form["grant_type"] == "authorization_code"
        return {"access_token": "a", "refresh_token": "r-" + form["code"], "scope": self.granted}


@pytest.fixture
def google(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8001/oauth/google/callback")
    monkeypatch.setattr(gc, "TOKENS", tmp_path / "tokens")
    f = FakeGoogle()
    monkeypatch.setattr(gc, "_http", f)
    return f


def _state(person_id):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(gc.connect_url(person_id)).query))["state"]


def test_connect_url_asks_only_for_what_airbyte_freebusy_needs(google):
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(gc.connect_url("g1")).query))
    assert q["scope"].split() == gc.SCOPES
    assert not any("events" in s or s.endswith("/calendar") for s in gc.SCOPES)  # no event details
    assert q["access_type"] == "offline" and q["client_id"] == "cid"


def test_accept_saves_only_the_refresh_token(google):
    assert gc.finish_connect("ketki", _state("g1")) == "g1"
    assert gc.is_connected("g1") and gc.refresh_token("g1") == "r-ketki"
    assert json.loads((gc.TOKENS / "g1.json").read_text()) == {"refresh_token": "r-ketki"}


def test_unticked_permission_is_refused(google):
    google.granted = gc.SCOPES[0]
    with pytest.raises(PermissionError):
        gc.finish_connect("ketki", _state("g1"))
    assert not gc.is_connected("g1")


def test_tampered_state_cannot_connect_someone_else(google):
    forged = "g2." + _state("g1").split(".", 1)[1]
    with pytest.raises(ValueError):
        gc.finish_connect("x", forged)
    assert not gc.is_connected("g2")


def test_disconnect_forgets_the_token(google):
    gc.finish_connect("ketki", _state("g1"))
    gc.disconnect("g1")
    assert not gc.is_connected("g1") and gc.refresh_token("g1") is None


def test_unsafe_ids_are_rejected(google):
    with pytest.raises(ValueError):
        gc.connect_url("../etc")
    assert not gc.is_connected("../etc")
