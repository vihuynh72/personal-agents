import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from agent import watcher
from agent.api import create_app
from agent.chat import Chat
from agent.llm import FakeLLM
from agent.payments import SessionStore, StripeTools
from agent.profiles import ProfileStore
from agent.workflow import Workflow
from contracts.fixtures import FakeTools
from contracts.models import Cart

ME = "+15550002222"


def _chat_order(tmp_path, tools):
    wf = Workflow(tools, FakeLLM(), str(tmp_path))
    c = Chat(wf, ProfileStore(str(tmp_path)), FakeLLM())
    c.handle(ME, "hi")
    c.handle(ME, "I'm allergic to peanuts")
    assert c.handle(ME, "get me coffee").startswith("Here's your cart")
    (gid,) = wf.ids("awaiting_payment")
    return wf, c, gid


def test_watcher_fulfils_once_and_queues_one_receipt(tmp_path):
    tools = FakeTools()
    wf, c, gid = _chat_order(tmp_path, tools)
    watcher.tick(wf)
    assert wf.get(gid).status == "awaiting_payment" and wf.outbox_pop() == []
    tools.paid = True
    for _ in range(3):
        watcher.tick(wf)
    assert wf.get(gid).status == "done"
    audit = wf.audit(gid)
    card = [e for e in audit if e.node_id == "F13.card"]
    assert len(card) == 1 and card[0].simulated and "simulated" in card[0].decision
    last4 = card[0].inputs["card_last4"]
    orders = [e for e in audit if e.node_id == "F13"]
    assert orders and all(e.simulated and f"ending {last4}" in e.decision and wf.get(gid).ship_to in e.decision
                          for e in orders)
    nodes = [e.node_id for e in audit]
    assert nodes.index("F13.card") < nodes.index("F13") < nodes.index("F9") < nodes.index("F11")

    client = TestClient(create_app(wf, c))
    msgs = client.get("/outbox").json()["messages"]
    assert len(msgs) == 2 and {m["sender"] for m in msgs} == {ME}  # the receipt, then one follow-up
    assert msgs[1]["text"].startswith("How was the")
    r = msgs[0]["text"]
    g = wf.get(gid)
    assert r.startswith("Paid. Order placed.") and "simulated" in r and len(r) < 900
    assert f"${g.cart.total:.2f}" in r and all(i.product.name in r for i in g.cart.items)
    assert client.get("/outbox").json() == {"messages": []}


def test_loop_survives_is_paid_errors(tmp_path):
    class Flaky(FakeTools):
        calls = 0

        def is_paid(self, cart):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("stripe down")
            return True

    wf, _, gid = _chat_order(tmp_path, Flaky())
    stop = watcher.start(wf, interval=0.01)
    try:
        for _ in range(200):
            if wf.get(gid).status == "done":
                break
            time.sleep(0.01)
    finally:
        stop.set()
    assert wf.get(gid).status == "done" and len(wf.outbox_pop()) == 2  # receipt + follow-up


def test_non_chat_gathering_queues_nothing(tmp_path):
    tools = FakeTools()
    wf = Workflow(tools, FakeLLM(), str(tmp_path))
    g = wf.approve_plan(wf.start("Vi", "dinner at my place Saturday", "1 Main St", ["g1", "g2"]).id)
    tools.paid = True
    watcher.tick(wf)
    assert wf.get(g.id).status == "done" and wf.outbox_pop() == []


def test_paid_text_checks_now(tmp_path):
    tools = FakeTools()
    wf, c, gid = _chat_order(tmp_path, tools)
    assert c.handle(ME, "I paid") == "I don't see the payment yet."
    tools.paid = True
    r = c.handle(ME, "I paid")
    assert r.startswith("Paid. Order placed.") and wf.get(gid).status == "done"
    out = wf.outbox_pop()  # the reply carried the receipt; no duplicate text, only the follow-up
    assert len(out) == 1 and out[0]["text"].startswith("How was the")


def test_stripe_session_id_survives_restart(tmp_path, monkeypatch):
    import stripe

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_offline")
    monkeypatch.setattr(stripe, "api_key", None)
    StripeTools(str(tmp_path))._sessions["abc"] = "cs_test_1"
    assert SessionStore(str(tmp_path)).get("abc") == "cs_test_1"
    fresh = StripeTools(str(tmp_path))
    seen = []
    monkeypatch.setattr(stripe.checkout.Session, "retrieve",
                        lambda sid: seen.append(sid) or SimpleNamespace(payment_status="paid", amount_subtotal=0))
    assert fresh.is_paid(Cart(gathering_id="abc", ship_to="x", items=[])) and seen == ["cs_test_1"]
    assert not fresh.is_paid(Cart(gathering_id="other", ship_to="x", items=[]))
