from fastapi.testclient import TestClient

from agent.api import create_app
from agent.chat import ONBOARD, Chat
from agent.llm import FakeLLM
from agent.profiles import ProfileStore
from agent.workflow import Workflow
from contracts.fixtures import FakeTools

ME = "+15550001111"


def _chat(tmp_path, tools=None):
    wf = Workflow(tools or FakeTools(), FakeLLM(), str(tmp_path))
    return Chat(wf, ProfileStore(str(tmp_path)), FakeLLM()), wf


def _onboarded(tmp_path, tools=None):
    c, wf = _chat(tmp_path, tools)
    assert c.handle(ME, "hi") == ONBOARD
    reply = c.handle(ME, "I'm allergic to peanuts and I like organic")
    assert "peanut" in reply and "organic" in reply and reply.endswith("What should I get you?")
    return c, wf


def test_onboarding_then_order_to_pay_link(tmp_path, monkeypatch):
    monkeypatch.delenv("WEB_URL", raising=False)
    c, wf = _onboarded(tmp_path)
    p = ProfileStore(str(tmp_path)).get(ME)
    assert (p.allergens, p.preferences) == (["peanut"], ["organic"])
    reply = c.handle(ME, "get me coffee")
    gid = next(f.stem for f in tmp_path.glob("*.json"))
    g = wf.get(gid)
    assert g.status == "awaiting_payment" and g.guest_ids == [ME]
    assert "$7.99" in reply and "No peanut" in reply and g.checkout_url in reply
    assert not any("peanut" in ing for i in g.cart.items for ing in i.product.ingredients)
    monkeypatch.setenv("WEB_URL", "https://app.example/")
    assert f"https://app.example/gatherings/{gid}" in c._cart(g)


def test_update_merges_preferences(tmp_path):
    c, _ = _onboarded(tmp_path)
    assert c.handle(ME, "actually I prefer Folgers now").startswith("Updated.")
    assert ProfileStore(str(tmp_path)).get(ME).preferences == ["organic", "folgers"]


def test_workflow_error_gives_apology(tmp_path):
    class Broken(FakeTools):
        def search_products(self, query, ship_to):
            raise RuntimeError("store down")

    c, _ = _onboarded(tmp_path, Broken())
    reply = c.handle(ME, "get me coffee")
    assert reply.startswith("Sorry") and "build your cart" in reply


def test_state_survives_restart(tmp_path):
    c, _ = _chat(tmp_path)
    c.handle(ME, "hi")
    c2, _ = _chat(tmp_path)  # new Chat and ProfileStore, same directory
    assert "What should I get you?" in c2.handle(ME, "I'm allergic to peanuts and I like organic")
    assert _chat(tmp_path)[0].handle(ME, "get me coffee").startswith("Here's your cart")


def test_unsafe_sender_cannot_escape(tmp_path):
    c, _ = _chat(tmp_path / "d")
    for bad in ["../../evil", "a/b", ".hidden", "x" * 100, ""]:
        assert c.handle(bad, "hi").startswith("Sorry")
    assert {f.parent for f in tmp_path.rglob("*") if f.is_file()} <= {tmp_path / "d" / "profiles"}
    assert not list(tmp_path.rglob("*evil*"))


def test_api_messages_and_profiles(tmp_path):
    c, wf = _chat(tmp_path)
    client = TestClient(create_app(wf, c, ProfileStore(str(tmp_path))))
    assert client.post("/messages", json={"sender": ME, "text": "hi"}).json() == {"reply": ONBOARD}
    assert client.get(f"/profiles/{ME}").status_code == 404
    body = {"id": "ignored", "name": "Sam", "allergens": ["egg"], "preferences": ["cheapest"]}
    assert client.put(f"/profiles/{ME}", json=body).json()["id"] == ME
    assert client.get(f"/profiles/{ME}").json()["preferences"] == ["cheapest"]
    assert client.put("/profiles/..%2Fx", json=body).status_code in (404, 409)
