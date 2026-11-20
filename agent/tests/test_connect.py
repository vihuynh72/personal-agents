import time
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from agent import connect
from agent.api import create_app
from agent.chat import ASK_ONE, ONBOARD, Chat
from agent.llm import FakeLLM
from agent.profiles import ProfileStore
from agent.workflow import Workflow
from contracts.fixtures import FakeTools
from contracts.models import GuestProfile

TOKEN = "ya29.SECRET-TOKEN-xyz"
LONG = "Your order of oat milk and gluten-free bread is on its way. " * 10


def _msg(subject, sender, date="Tue, 14 Oct 2026 18:30:00 -0700", snippet=LONG):
    return {"snippet": snippet, "payload": {"headers": [
        {"name": "Subject", "value": subject}, {"name": "From", "value": sender}, {"name": "Date", "value": date}]}}


MSGS = {"m1": _msg("Your Instacart order receipt", "Instacart <orders@instacart.com>"),
        "m2": _msg("Reservation confirmed at Nopa", "OpenTable <no-reply@opentable.com>", snippet="Party of 2"),
        "m3": _msg("New running shoes order", "Shop <x@shoes.com>"),
        "m4": _msg("Security alert for your account", "Google <no-reply@google.com>")}
EVENTS = [{"summary": "Dinner with Sam", "location": "Zuni Cafe", "start": {"dateTime": "2026-09-01T19:00:00-07:00"}},
          {"summary": "Sprint planning", "start": {"dateTime": "2026-09-02T10:00:00-07:00"}},
          {"summary": "Boba run", "start": {"date": "2026-09-03"}}]


class Fetcher:
    def __init__(self):
        self.calls = []

    def __call__(self, url, params):
        self.calls.append((url, params))
        if url.endswith("/messages"):
            return {"messages": [{"id": k} for k in MSGS]}
        if "/messages/" in url:
            return MSGS[url.rsplit("/", 1)[1]]
        return {"items": EVENTS}


def test_gmail_items_trim_drop_noise_and_never_ask_for_body():
    f = Fetcher()
    items = connect.gmail_items(f)
    assert [i["source"] for i in items] == ["receipt", "message"]
    assert items[0]["text"].startswith("Instacart: Your Instacart order receipt. Your order of oat milk")
    assert len(items[0]["text"]) <= len("Instacart: Your Instacart order receipt. ") + 200
    assert items[0]["when"] == "2026-10-14T18:30:00-07:00"
    for url, p in f.calls:
        if "/messages/" in url:
            assert p["format"] == "metadata" and "body" not in str(p) and "parts" not in str(p)
    assert "newer_than:1y" in f.calls[0][1]["q"] and f.calls[0][1]["maxResults"] == 40


def test_calendar_items_keep_food_events():
    items = connect.calendar_items(Fetcher())
    assert items == [{"text": "Calendar: Dinner with Sam at Zuni Cafe", "source": "calendar",
                      "when": "2026-09-01T19:00:00-07:00"},
                     {"text": "Calendar: Boba run", "source": "calendar", "when": "2026-09-03"}]


def test_state_single_use_and_expires(tmp_path, monkeypatch):
    s = connect.new_state(tmp_path, "+15551234567")
    assert connect.take_state(tmp_path, s) == "+15551234567"
    assert connect.take_state(tmp_path, s) is None
    s2 = connect.new_state(tmp_path, "rowan")
    monkeypatch.setattr(time, "time", lambda: 10**12)
    assert connect.take_state(tmp_path, s2) is None
    with pytest.raises(ValueError):
        connect.new_state(tmp_path, "../etc")


@pytest.fixture
def off(monkeypatch):
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "PUBLIC_URL"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("PUBLIC_URL", "https://agent.test")


class StubMemory:
    def __init__(self, store):
        self.store, self.calls = store, []

    def add_many(self, pid, items):
        self.calls.append((pid, items))
        p = self.store.save(GuestProfile(id=pid, name=pid, allergens=["peanut"], preferences=["oat milk"]))
        return {"profile": p, "added": [{"kind": "allergen"}], "conflicts": [{"value": "x"}]}


def _client(tmp_path):
    store = ProfileStore(str(tmp_path))
    wf = Workflow(FakeTools(), FakeLLM(), str(tmp_path), profiles=store)
    mem = StubMemory(store)
    return TestClient(create_app(wf, profiles=store, memory=mem)), wf, mem, store


def test_connect_503_when_unconfigured(tmp_path, off):
    c, *_ = _client(tmp_path)
    assert c.get("/connect/google", params={"sender": "rowan"}).status_code == 503
    assert c.get("/connect/google/callback", params={"code": "x", "state": "y"}).status_code == 503


def test_connect_redirects_and_callback_imports_once(tmp_path, on, monkeypatch):
    c, wf, mem, store = _client(tmp_path)
    assert c.get("/connect/google", params={"sender": "../x"}, follow_redirects=False).status_code == 400
    r = c.get("/connect/google", params={"sender": "+15551234567"}, follow_redirects=False)
    assert r.status_code == 302
    url = urllib.parse.urlparse(r.headers["location"])
    q = urllib.parse.parse_qs(url.query)
    assert url.netloc == "accounts.google.com" and url.path == "/o/oauth2/v2/auth"
    assert q["scope"] == [connect.SCOPES] and q["redirect_uri"] == ["https://agent.test/connect/google/callback"]
    assert q["response_type"] == ["code"] and q["access_type"] == ["online"] and q["client_id"] == ["cid"]

    store.set_pending("+15551234567", True)
    monkeypatch.setattr(connect, "exchange", lambda cfg, code: TOKEN)
    monkeypatch.setattr(connect, "make_fetcher", lambda tok: Fetcher() if tok == TOKEN else None)
    monkeypatch.setattr(connect, "start", lambda fn: fn())
    r = c.get("/connect/google/callback", params={"code": "abc", "state": q["state"][0]})
    assert r.status_code == 200 and "Connected" in r.text and "discarded" in r.text
    assert len(mem.calls) == 1 and mem.calls[0][0] == "+15551234567" and len(mem.calls[0][1]) == 4
    out = wf.outbox_pop()
    assert len(out) == 1 and out[0]["sender"] == "+15551234567"
    assert "peanut" in out[0]["text"] and "1 things I wasn't sure about" in out[0]["text"]
    assert not store.pending("+15551234567")
    assert c.get("/connect/google/callback", params={"code": "abc", "state": q["state"][0]}).status_code == 400
    for p in tmp_path.rglob("*"):
        if p.is_file():
            assert TOKEN not in p.read_text(errors="ignore")


def test_import_failure_texts_the_sender(tmp_path):
    store = ProfileStore(str(tmp_path))
    wf = Workflow(FakeTools(), FakeLLM(), str(tmp_path), profiles=store)

    def boom(url, params):
        raise RuntimeError("HTTP 403")
    connect.run_import("rowan", boom, StubMemory(store), wf, store)
    assert wf.outbox_pop() == [{"sender": "rowan", "text": "I couldn't read your Google account (HTTP 403). "
                                                           "No problem: just tell me anything you can't have."}]


def test_onboarding_texts(tmp_path, off, monkeypatch):
    store = ProfileStore(str(tmp_path))
    chat = Chat(Workflow(FakeTools(), FakeLLM(), str(tmp_path), profiles=store), store, FakeLLM())
    assert chat.handle("a1", "hi") == ONBOARD
    assert chat.handle("a2", "get me coffee") == ASK_ONE
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    link = "https://personal-agents-production-81468651.up.railway.app/connect/google?sender=%2B15550001111"
    assert chat.handle("+15550001111", "hi") == ONBOARD + " Or skip the question: connect Google and I'll learn " \
                                                          "from your receipts: " + link
    assert chat.handle("b2", "get me coffee").startswith(ASK_ONE + " Or skip the question")
