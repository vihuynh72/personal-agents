import json

import pytest
from fastapi.testclient import TestClient

from agent.a2a import Connections, PersonAgent, _msg, plan_gathering, shopping_request
from agent.api import create_app
from agent.llm import _FORBIDDEN, _STEAKHOUSE, _VARIED, FakeLLM
from agent.profiles import ProfileStore
from agent.workflow import _matches
from contracts.fixtures import FakeTools
from contracts.models import GuestProfile

TIMES = ["2026-11-28T19:00", "2026-11-27T19:00"]
GUESTS = ["g1", "g2", "g3"]


@pytest.fixture
def env(tmp_path):
    store, conns = ProfileStore(str(tmp_path)), Connections(str(tmp_path))
    store.save(GuestProfile(id="host", name="Hana"))
    store.save(GuestProfile(id="g1", name="Asha", restrictions=["vegetarian"], preferences=["organic"], contact="+15550001"))
    store.save(GuestProfile(id="g2", name="Ben", allergens=["egg"], preferences=["folgers"], contact="+15550002"))
    store.save(GuestProfile(id="g3", name="Chen", allergens=["peanut"], preferences=["cheapest"], contact="+15550003"))
    for g in GUESTS:
        conns.grant(g, "host", {"dietary", "availability"})
    return store, conns


def _plan(env, request="dinner party for four", guests=GUESTS, tools=None, **kw):
    store, conns = env
    return plan_gathering("host", guests, request, TIMES, store, conns, tools or FakeTools(), FakeLLM(), **kw)


def test_agreed_menu_is_safe_and_private(env):
    plan = _plan(env)
    assert plan["status"] == "agreed" and plan["rounds"] == 1 and plan["time"] == "2026-11-27T19:00"
    menu = {d["name"]: d for d in plan["menu"]}
    banned = {"g1": _FORBIDDEN["vegetarian"], "g2": ["egg"], "g3": ["peanut"]}
    for g, info in plan["per_guest"].items():
        assert len(info["can_eat"]) >= 2 and any(menu[n]["main"] for n in info["can_eat"])
        assert not any(_matches(b, i) for n in info["can_eat"] for i in menu[n]["ingredients"] for b in banned[g])
    reply = next(m for m in plan["transcript"] if m["type"] == "constraints.reply" and m["from"] == "g2")
    assert reply["body"]["constraints"] == [{"avoid": "egg", "hard": True}]
    for m in plan["transcript"]:
        assert set(m) == {"type", "from", "to", "id", "body"}
        if m["type"] == "constraints.reply":
            assert all(set(c) == {"avoid", "hard"} for c in m["body"]["constraints"])
    text = json.dumps(plan["transcript"]).lower()
    for word in ["allerg", "vegetarian", "organic", "folgers", "cheapest", "+1555"]:
        assert word not in text
    assert shopping_request(plan).startswith("ingredients for: Vegetable pasta primavera") and "for 4 people" in shopping_request(plan)


def test_no_consent_is_refused_and_excluded(env):
    store, conns = env
    conns.revoke("g3", "host")
    r = PersonAgent("g3", store, conns, llm=FakeLLM()).handle(_msg("constraints.request", "host", "g3", {}))
    assert r["type"] == "refused" and r["body"]["reason"] == "no consent"
    plan = _plan(env)
    assert plan["no_consent"] == ["g3"] and "g3" not in plan["per_guest"] and plan["status"] == "agreed"


def test_steakhouse_counters_then_agrees(env):
    plan = _plan(env, "steakhouse dinner")
    assert plan["status"] == "agreed" and plan["rounds"] == 2
    assert any(m["type"] == "counter" for m in plan["transcript"])
    assert {d["name"] for d in plan["menu"]} == {d["name"] for d in _VARIED}


def test_impossible_needs_host(env):
    store, _ = env
    every = {i for d in _VARIED + _STEAKHOUSE for i in d["ingredients"]}
    store.save(GuestProfile(id="g1", name="Asha", allergens=sorted(every)))
    plan = _plan(env, max_rounds=3)
    assert plan["status"] == "needs_host" and plan["rounds"] == 3 and plan["unresolved"]


def test_no_common_time(env):
    class Busy(FakeTools):
        def free_times(self, pid, cands):
            return [] if pid == "g2" else cands
    assert _plan(env, tools=Busy())["status"] == "no_common_time"


def test_unsafe_ids_rejected(env, tmp_path):
    store, conns = env
    with pytest.raises(ValueError):
        conns.grant("../x", "host", {"dietary"})
    with pytest.raises(ValueError):
        PersonAgent("../etc", store, conns)
    with pytest.raises(ValueError):
        conns.grant("g1", "host", {"contact"})


def test_endpoints(tmp_path):
    class WF:
        tools, llm = FakeTools(), FakeLLM()
    store = ProfileStore(str(tmp_path))
    c = TestClient(create_app(WF(), profiles=store))
    for p in [GuestProfile(id="host", name="H"), GuestProfile(id="g1", name="A", restrictions=["vegetarian"])]:
        assert c.put(f"/profiles/{p.id}", json=p.model_dump()).status_code == 200
    assert c.post("/a2a/consent", json={"owner": "g1", "to": "host", "scopes": ["dietary", "availability"]}).json() == \
        {"scopes": ["availability", "dietary"]}
    plan = c.post("/a2a/plan", json={"host": "host", "guests": ["g1"], "request": "dinner",
                                     "candidate_times": TIMES}).json()
    assert plan["status"] == "agreed"
    r = c.post("/a2a/message", json={"message": _msg("proposal", "host", "g1", {"menu": _STEAKHOUSE})}).json()
    assert r["type"] == "counter" and "beef" in r["body"]["need"]
    assert c.post("/a2a/consent", json={"owner": "../x", "to": "host", "scopes": ["dietary"]}).status_code == 409
