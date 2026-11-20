from fastapi.testclient import TestClient

from agent.api import create_app
from agent.chat import ASK_ONE, ONBOARD, Chat
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
    assert "peanut" in reply and "organic" in reply and reply.endswith("Text me what you need any time.")
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
    assert "$7.99" in reply and "No peanut" in reply and f"/cart/{gid}" in reply and g.checkout_url not in reply
    assert not any("peanut" in ing for i in g.cart.items for ing in i.product.ingredients)
    monkeypatch.setenv("PUBLIC_URL", "https://app.example/")
    assert f"Review and pay: https://app.example/cart/{gid}" in c._cart(g)


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
    assert "Text me what you need" in c2.handle(ME, "I'm allergic to peanuts and I like organic")
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


def _gids(wf):
    return sorted((wf.get(f.stem) for f in wf.dir.glob("*.json")), key=lambda g: g.id)


def test_request_first_asks_one_question_then_shops(tmp_path):
    c, wf = _chat(tmp_path)
    assert c.handle(ME, "get me coffee") == ASK_ONE
    reply = c.handle(ME, "I'm allergic to peanuts")
    assert "Here's your cart" in reply and "No peanut (you)" in reply and "?" not in reply
    assert ProfileStore(str(tmp_path)).get(ME).allergens == ["peanut"]
    assert f"/cart/{wf.gatherings_of(ME)[0]}" in reply


def test_none_means_empty_profile_and_dinner_still_gets_a_cart(tmp_path):
    c, wf = _chat(tmp_path)
    assert c.handle(ME, "what's for dinner") == ASK_ONE
    reply = c.handle(ME, "none")
    p = ProfileStore(str(tmp_path)).get(ME)
    assert (p.allergens, p.restrictions, p.preferences) == ([], [], [])
    g = wf.get(wf.gatherings_of(ME)[0])
    assert g.mode == "self" and 2 <= len(g.cart.items) <= 4 and "Here's your cart" in reply


def test_greeting_paths(tmp_path):
    c, _ = _chat(tmp_path / "a")
    assert c.handle(ME, "hi") == ONBOARD
    assert "Here's your cart" in c.handle(ME, "I'm Sam, allergic to peanuts, get me coffee")
    c, _ = _chat(tmp_path / "b")
    c.handle(ME, "hello")
    assert c.handle(ME, "nothing").startswith("Saved. Avoiding: nothing.")
    assert c.handle(ME, "get me coffee").startswith("Here's your cart")  # known sender: zero questions


def test_name_in_reasons(tmp_path):
    c, _ = _chat(tmp_path)
    c.handle(ME, "get me coffee")
    assert "No peanut (Sam)" in c.handle(ME, "I'm Sam and allergic to peanuts")


def test_never_two_questions_in_a_row(tmp_path):
    scripts = [["hi", "hmm", "ok", "get me coffee"], ["get me coffee", "none", "is it good?"],
               ["what's for dinner", "no"], ["hey", "I'm allergic to peanuts"], ["hi", "none", "hello"]]
    for n, script in enumerate(scripts):
        c, _ = _chat(tmp_path / str(n))
        replies = [c.handle(ME, m) for m in script]
        asks = ["?" in r and not r.startswith("Here's your cart") for r in replies]
        assert not any(a and b for a, b in zip(asks, asks[1:])), (script, replies)


class SafeSayingLLM(FakeLLM):
    def system2(self, prompt):
        return "Yes, it's totally safe for you!" if "TASK: answer" in prompt else super().system2(prompt)


def test_question_answered_from_cart_without_assurance(tmp_path):
    c, wf = _onboarded(tmp_path)
    c.handle(ME, "get me coffee")
    g = wf.get(wf.gatherings_of(ME)[0])
    for chat in (c, Chat(wf, ProfileStore(str(tmp_path)), SafeSayingLLM())):
        r = chat.handle(ME, "is this safe? anything about cross-contamination?")
        assert not r.startswith("Here's your cart") and g.checkout_url not in r
        assert "safe" not in r.lower() and "cross-contamination" in r and "check the package" in r
        assert "arabica coffee" in r
    assert wf.get(g.id).status == "awaiting_payment"


def test_change_replaces_cart_and_stops_old(tmp_path):
    c, wf = _onboarded(tmp_path)
    c.handle(ME, "get me coffee")
    old = wf.gatherings_of(ME)[0]
    reply = c.handle(ME, "organic instead")
    new = wf.gatherings_of(ME)[-1]
    assert new != old and wf.get(old).status == "stopped" and wf.get(new).status == "awaiting_payment"
    assert "Correction: organic instead" in wf.get(new).request and wf.get(new).menu == ["organic ground coffee"]
    assert reply.startswith("Here's your cart") and f"/cart/{new}" in reply


def test_drill_adapter_runs_the_real_conversation(tmp_path, monkeypatch):
    from agent import drill_adapter
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "STRIPE_SECRET_KEY", "SENSO_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(drill_adapter, "_chat", None)
    client = TestClient(drill_adapter.app)
    assert client.post("/chat", json={"message": "get me coffee", "session": "s1"}).json() == {"reply": ASK_ONE}
    assert client.post("/chat", json={"message": "get me coffee", "session": "s2"}).json() == {"reply": ASK_ONE}
    assert "Here's your cart" in client.post("/chat", json={"message": "none", "session": "s1"}).json()["reply"]


def test_intent_falls_back_when_the_model_fails(tmp_path):
    from agent.chat import Chat
    from agent.profiles import ProfileStore

    class Broken(FakeLLM):
        def system1(self, prompt):
            if "TASK: intent" in prompt:
                raise RuntimeError("model down")
            return super().system1(prompt)

    store = ProfileStore(str(tmp_path))
    chat = Chat(Workflow(FakeTools(), Broken(), str(tmp_path), profiles=store), store, Broken())
    assert chat._intent("is this ok for my allergy?") == "question"
    assert "couldn't" not in chat.handle("+15550003333", "get me coffee")
