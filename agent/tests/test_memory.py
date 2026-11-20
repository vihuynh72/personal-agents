import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.api import create_app
from agent.llm import FakeLLM
from agent.memory import Memory
from agent.profiles import ProfileStore

SAMPLE = Path(__file__).resolve().parents[2] / "demo" / "sample_history.json"


def mem(tmp_path):
    return Memory(ProfileStore(str(tmp_path)), FakeLLM(), str(tmp_path))


def test_newer_dislike_beats_older_like_and_keeps_the_old_fact(tmp_path):
    m = mem(tmp_path)
    m.add("p1", "I love cilantro", "message", "2025-01-01")
    r = m.add("p1", "I can't stand cilantro", "message", "2026-01-01")
    assert "cilantro" not in r["profile"].preferences and "no cilantro" in r["profile"].restrictions
    assert r["conflicts"][0]["rule"] == "newer statement wins"
    old, new = m.history("p1")
    assert old["status"] == "superseded" and old["superseded_by"] == new["id"] and new["status"] == "active"


def test_inferred_negative_allergen_keeps_the_allergy(tmp_path):
    m = mem(tmp_path)
    m.add("p1", "I'm allergic to peanuts", "chat", "2025-01-01")
    r = m.add("p1", "I can eat peanuts now", "receipt", "2026-01-01")
    assert r["profile"].allergens == ["peanut"]
    assert r["conflicts"][0]["needs_confirmation"] is True and r["conflicts"][0]["rule"].startswith("safety")


def test_direct_newer_negative_allergen_removes_it(tmp_path):
    m = mem(tmp_path)
    m.add("p1", "I'm allergic to peanuts", "message", "2025-01-01")
    r = m.add("p1", "I can eat peanuts now, the allergy was a misdiagnosis", "chat", "2026-01-01")
    assert r["profile"].allergens == [] and len(m.history("p1")) == 2


def test_preference_for_an_allergen_is_superseded(tmp_path):
    m = mem(tmp_path)
    m.add("p1", "allergic to peanuts", "chat", "2025-01-01")
    r = m.add("p1", "Bought peanut butter", "receipt", "2026-01-01")
    assert "peanut butter" not in r["profile"].preferences
    assert r["conflicts"][0]["rule"] == "safety: allergen overrides preference"


def test_duplicates_collapse_to_newest(tmp_path):
    m = mem(tmp_path)
    for d in ("2025-01-01", "2025-06-01", "2026-01-01"):
        m.add("p1", "organic please", "receipt", d)
    active = [f for f in m.history("p1") if f["status"] == "active"]
    assert [f["when"][:10] for f in active] == ["2026-01-01"]
    assert m.store.get("p1").preferences == ["organic"]


def test_loop_terminates_on_a_pile_of_contradictions(tmp_path):
    m = mem(tmp_path)
    items = [{"text": t, "source": s, "when": f"2025-01-{i + 1:02d}"} for i, (t, s) in enumerate(
        [("I love kale", "message"), ("I can't stand kale", "message")] * 6 +
        [("allergic to soy", "chat"), ("I can eat soy now", "receipt"), ("I love soy", "message")] * 4)]
    r = m.add_many("p1", items)
    assert m.last_iterations <= 5
    assert r["profile"].allergens == ["soy"] and "no kale" in r["profile"].restrictions
    assert [f for f in m.history("p1") if f["status"] == "active" and f["value"] == "kale"][0]["kind"] == "dislike"
    assert m.add_many("p1", [])["conflicts"] == []  # the rewritten memory is stable on restart


def test_saved_profile_equals_rebuilt(tmp_path):
    m = mem(tmp_path)
    r = m.add("p1", "I'm Rowan, allergic to eggs, I love tofu", "chat")
    assert m.store.get("p1") == r["profile"] and r["profile"].name == "Rowan"


def test_unsafe_id_rejected(tmp_path):
    with pytest.raises(ValueError):
        mem(tmp_path).add("../etc", "I love kale", "chat")


def test_sample_history(tmp_path):
    r = mem(tmp_path).add_many("rowan", json.loads(SAMPLE.read_text())["items"])
    p = r["profile"]
    assert p.allergens == ["peanut"] and "cilantro" not in p.preferences and "no cilantro" in p.restrictions
    assert "organic" in p.preferences and "folgers" in p.preferences
    assert not any("peanut" in x for x in p.preferences)


def test_endpoints(tmp_path):
    store = ProfileStore(str(tmp_path))
    c = TestClient(create_app(object(), profiles=store, memory=Memory(store, FakeLLM(), str(tmp_path))))
    r = c.post("/profiles/rowan/import", json={"items": json.loads(SAMPLE.read_text())["items"]}).json()
    assert r["profile"]["allergens"] == ["peanut"] and r["added"] > 0 and r["conflicts"]
    assert len(c.get("/profiles/rowan/memory").json()) >= r["added"]
    assert c.post("/profiles/..bad/import", json={"items": []}).status_code == 409
