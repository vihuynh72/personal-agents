from datetime import datetime, timedelta, timezone

import pytest

from tools import cognee as cognee_mod
from tools import google_calendar as gc
from tools.availability import AIRBYTE, SIMULATED, availability, decide, forget, record_text, records, replace_record
from tools.cognee import Cognee
from tools.sync_calendars import sync_person
from tools.tests.test_cognee import FakeCognee

PT = timezone(timedelta(hours=-8))
START = datetime(2026, 11, 21, 19, 0, tzinfo=PT)
END = START + timedelta(hours=2)
WINDOW = ("2026-11-14T00:00:00Z", "2026-12-31T00:00:00Z")
NOW = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setenv("COGNEE_URL", "https://cognee.test")
    monkeypatch.setenv("COGNEE_API_KEY", "k")
    f = FakeCognee()
    monkeypatch.setattr(cognee_mod, "_http", f)
    monkeypatch.setattr(gc, "TOKENS", tmp_path / "tokens")
    return f


def _rec(busy, window=WINDOW, synced_at="2026-11-20T22:00:00Z"):
    return {"person_id": "g1", "busy": busy, "window": list(window), "source": AIRBYTE, "synced_at": synced_at}


def test_decide_free_busy_pending():
    assert decide(None, START, END, NOW).status == "pending"
    assert decide(_rec([]), START, END, NOW).status == "free"
    clash = {"start": "2026-11-21T19:30:00-08:00", "end": "2026-11-21T20:00:00-08:00"}
    assert decide(_rec([clash]), START, END, NOW).status == "busy"
    touching = {"start": "2026-11-21T21:00:00-08:00", "end": "2026-11-21T22:00:00-08:00"}  # starts as dinner ends
    assert decide(_rec([touching]), START, END, NOW).status == "free"
    utc = {"start": "2026-11-22T03:30:00Z", "end": "2026-11-22T04:00:00Z"}  # 7:30 PM Pacific, written in UTC
    assert decide(_rec([utc]), START, END, NOW).status == "busy"
    old = ("2026-10-01T00:00:00Z", "2026-11-15T00:00:00Z")
    assert decide(_rec([], old), START, END, NOW).status == "pending"  # not read for Saturday: unknown, not free


def test_availability_reads_cognee_and_labels_the_source(fake):
    c = Cognee()
    replace_record(c, "g1", record_text("g1", "Ketki", [], WINDOW, AIRBYTE, "2026-11-20T22:00:00Z"))
    replace_record(c, "g3", record_text("g3", "Jamie", [{"start": "2026-11-21T18:30:00-08:00",
                                                         "end": "2026-11-21T19:30:00-08:00"}],
                                        WINDOW, SIMULATED, "t"))
    out = availability(["g1", "g3", "g6"], START, END, now=NOW)
    assert (out["g1"].status, out["g1"].source) == ("free", AIRBYTE)
    assert (out["g3"].status, out["g3"].source) == ("busy", SIMULATED)
    assert (out["g6"].status, out["g6"].source) == ("pending", None)


def test_replace_keeps_one_record_per_person_and_forget_removes_it(fake):
    c = Cognee()
    replace_record(c, "g1", record_text("g1", "Ketki", [], WINDOW, AIRBYTE, "1"))
    replace_record(c, "g1", record_text("g1", "Ketki", [], WINDOW, AIRBYTE, "2"))
    assert len(fake.data["guest_availability"]) == 1 and records(c)["g1"][1]["synced_at"] == "2"
    forget(c, "g1")
    assert records(c) == {}


def test_sync_person_stores_what_airbyte_read(fake):
    (gc.TOKENS).mkdir(parents=True)
    (gc.TOKENS / "g1.json").write_text('{"refresh_token": "r"}')
    seen = []

    def reader(token):
        seen.append(token)
        return [{"start": "2026-11-21T19:30:00-08:00", "end": "2026-11-21T20:00:00-08:00"}]

    assert sync_person("g1", "Ketki", reader=reader, now=NOW) == 1
    assert seen == ["r"]
    a = availability(["g1"], START, END, now=NOW)["g1"]
    assert (a.status, a.source, a.synced_at) == ("busy", AIRBYTE, "2026-11-20T22:00:00Z")


def test_sync_refuses_people_who_did_not_connect(fake):
    with pytest.raises(LookupError):
        sync_person("g4", "Ryan", reader=lambda t: [], now=NOW)
    assert records(Cognee()) == {}


def test_naive_times_are_rejected(fake):
    with pytest.raises(ValueError):
        availability(["g1"], START.replace(tzinfo=None), END)


def test_stale_real_calendar_is_pending_but_simulated_is_not():
    late = NOW + timedelta(minutes=31)
    assert decide(_rec([]), START, END, late).status == "pending"
    sim = dict(_rec([]), source=SIMULATED, synced_at="2026-11-01T00:00:00Z")
    assert decide(sim, START, END, late).status == "free"


def test_auto_sync_covers_every_connected_person_and_survives_one_failure(fake):
    from tools.sync_calendars import sync_all

    gc.TOKENS.mkdir(parents=True)
    for pid, tok in [("g1", "ok"), ("g4", "bad")]:
        (gc.TOKENS / f"{pid}.json").write_text('{"refresh_token": "%s"}' % tok)

    def reader(token):
        if token == "bad":
            raise RuntimeError("revoked")
        return []

    out = sync_all({"g1": "Ketki", "g4": "Ryan"}, reader=reader)
    assert out["g1"] == 0 and out["g4"].startswith("failed")
    assert set(records(Cognee())) == {"g1"}  # Ryan's failure wrote nothing, so Ryan stays pending
