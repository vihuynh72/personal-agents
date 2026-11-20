"""Post-order follow-up (F11) and feedback into memory, with an in-test fake of agent.memory.Memory."""
import time

from agent import watcher
from agent.chat import Chat
from agent.llm import FakeLLM
from agent.profiles import ProfileStore
from agent.workflow import Workflow
from contracts.fixtures import FakeTools
from contracts.models import GuestProfile

ME, HOST, BEN = "+15550004444", "+15550005555", "+15550006666"


class FakeMemory:
    """Same interface as agent.memory.Memory; naively copies any allergen word it sees, to prove chat blocks that."""

    def __init__(self, store, conflicts=()):
        self.store, self.calls, self.conflicts = store, [], list(conflicts)

    def add(self, person_id, text, source, when=None):
        self.calls.append((person_id, text, source))
        p = self.store.get(person_id) or GuestProfile(id=person_id, name=person_id)
        added = [{"kind": "dislike", "value": "the coffee", "polarity": "+"}] if "bitter" in text else []
        if "egg" in text:
            p = p.model_copy(update={"allergens": p.allergens + ["egg"]})
        self.store.save(p)
        return {"profile": p, "added": added, "conflicts": self.conflicts}


def _paid(tmp_path, memory=None, tools=None):
    tools = tools or FakeTools()
    store = ProfileStore(str(tmp_path))
    wf = Workflow(tools, FakeLLM(), str(tmp_path), profiles=store)
    c = Chat(wf, store, FakeLLM(), memory(store) if memory else None)
    c.handle(ME, "hi")
    c.handle(ME, "none")
    c.handle(ME, "get me coffee")
    tools.paid = True
    return wf, c, tools, store


def test_receipt_then_one_followup_and_feedback_into_memory(tmp_path):
    wf, c, _, store = _paid(tmp_path, FakeMemory)
    watcher.tick(wf)
    watcher.tick(wf)
    out = wf.outbox_pop()
    assert [m["sender"] for m in out] == [ME, ME]
    assert out[0]["text"].startswith("Paid.") and out[1]["text"].startswith("How was the")
    assert out[1]["text"].count("?") == 2 and "Ground Coffee" in out[1]["text"]
    watcher.tick(wf)
    assert wf.outbox_pop() == []
    gid = wf.gatherings_of(ME)[0]
    assert any(e.node_id == "F11" and "1 people" in e.decision for e in wf.audit(gid))
    assert wf.awaiting(ME)["gathering_id"] == gid

    reply = c.handle(ME, "the coffee was too bitter")
    assert c.memory.calls == [(ME, "the coffee was too bitter", "feedback")]
    assert reply == "Thanks. Noted: you didn't like the coffee." and wf.awaiting(ME) is None
    assert any(e.node_id == "F11" and e.inputs.get("feedback") == "the coffee was too bitter" for e in wf.audit(gid))
    assert c.handle(ME, "the coffee was too bitter").startswith("Tell me what to get")  # no longer awaiting
    assert wf.outbox_pop() == []  # never a follow-up about a follow-up


def test_conflict_needing_confirmation_asks_exactly_one_question(tmp_path):
    wf, c, _, _ = _paid(tmp_path, lambda s: FakeMemory(s, [{"value": "the coffee", "rule": "x", "needs_confirmation": True},
                                                            {"value": "milk", "rule": "y", "needs_confirmation": True}]))
    watcher.tick(wf)
    reply = c.handle(ME, "the coffee was too bitter")
    assert reply.count("?") == 1 and "the coffee" in reply.split("Noted:")[1]


def test_cheap_reply_and_order_while_awaiting(tmp_path):
    wf, c, _, _ = _paid(tmp_path, lambda s: FakeMemory(s, [{"value": "x", "rule": "r", "needs_confirmation": True}]))
    watcher.tick(wf)
    assert c.handle(ME, "good, thanks") == "Thanks!" and c.memory.calls == [] and wf.awaiting(ME) is None
    for text in ("👍", "no", "nothing", "fine"):
        wf._update("awaiting.json", {}, lambda d: d.__setitem__(ME, {"gathering_id": wf.gatherings_of(ME)[0],
                                                                     "person": ME, "role": "host"}))
        assert c.handle(ME, text) == "Thanks!"
    wf._update("awaiting.json", {}, lambda d: d.__setitem__(ME, {"gathering_id": wf.gatherings_of(ME)[0],
                                                                 "person": ME, "role": "host"}))
    assert c.handle(ME, "get me coffee").startswith("Here's your cart")  # an order is still an order
    assert c.memory.calls == []


def test_delay_holds_the_followup(tmp_path, monkeypatch):
    monkeypatch.setenv("FEEDBACK_DELAY_SECONDS", "0.2")
    wf, *_ = _paid(tmp_path)
    watcher.tick(wf)
    assert [m["text"][:5] for m in wf.outbox_pop()] == ["Paid."]
    watcher.tick(wf)
    assert wf.outbox_pop() == []
    time.sleep(0.25)
    fresh = Workflow(FakeTools(), FakeLLM(), str(tmp_path))  # a restart keeps the pending follow-up
    watcher.tick(fresh)
    watcher.tick(fresh)
    assert [m["text"][:11] for m in fresh.outbox_pop()] == ["How was the"]


def test_dinner_guest_feedback_reaches_host_without_allergens(tmp_path):
    tools = FakeTools()
    store = ProfileStore(str(tmp_path))
    store.save(GuestProfile(id="g2", name="Ben", allergens=["egg"], contact=BEN))
    store.save(GuestProfile(id=HOST, name="Vi"))
    wf = Workflow(tools, FakeLLM(), str(tmp_path), profiles=store)
    mem = FakeMemory(store)
    c = Chat(wf, store, FakeLLM(), mem)
    g = wf.start("Vi", "dinner at my place Saturday", "1 Main St", ["g1", "g2"])
    wf.set_sender(g.id, HOST)
    wf.approve_plan(g.id)
    tools.paid = True
    watcher.tick(wf)
    out = wf.outbox_pop()
    assert [m["sender"] for m in out] == [HOST, HOST, BEN]  # receipt, then one follow-up each
    assert any(e.node_id == "F11" and "2 people" in e.decision for e in wf.audit(g.id))

    text = "the marinara sauce was too salty, and I can't have egg"
    assert c.handle(BEN, text).startswith("Thanks")
    assert mem.calls[0] == ("g2", text, "feedback")
    assert mem.calls[1] == (HOST, f"Guest Ben said about marinara sauce: {text}", "guest")
    assert store.get(HOST).allergens == [] and store.get(HOST).restrictions == []


def test_without_memory_everything_still_works(tmp_path):
    wf, c, _, store = _paid(tmp_path)
    watcher.tick(wf)
    assert len(wf.outbox_pop()) == 2
    assert c.handle(ME, "the coffee was too bitter") == "Thanks, noted." and wf.awaiting(ME) is None
    gid = wf.gatherings_of(ME)[0]
    assert any(e.node_id == "F11" and e.inputs.get("feedback") == "the coffee was too bitter" for e in wf.audit(gid))


def test_onboarding_and_update_go_through_memory(tmp_path):
    store = ProfileStore(str(tmp_path))
    mem = FakeMemory(store)
    c = Chat(Workflow(FakeTools(), FakeLLM(), str(tmp_path), profiles=store), store, FakeLLM(), mem)
    c.handle(ME, "hi")
    assert c.handle(ME, "I can't have egg").startswith("Saved. Avoiding: egg.")
    assert c.handle(ME, "actually I'm allergic to egg").startswith("Updated.")
    assert [s for *_, s in mem.calls] == ["chat", "chat"]


def test_safety_question_yes_keeps_and_no_removes(tmp_path):
    from agent.chat import Chat
    from agent.profiles import ProfileStore

    calls = []

    class Mem:
        def add(self, person_id, text, source, when=None):
            calls.append((text, source))
            return {"profile": None, "added": [], "conflicts": []}

    store = ProfileStore(str(tmp_path))
    chat = Chat(Workflow(FakeTools(), FakeLLM(), str(tmp_path), profiles=store), store, FakeLLM(), memory=Mem())
    chat._asked["+15550004444"] = "peanut"
    assert "Still avoiding peanut" in chat.handle("+15550004444", "yes") and not calls
    chat._asked["+15550004444"] = "peanut"
    assert "stop avoiding peanut" in chat.handle("+15550004444", "No!")
    assert calls and calls[0][1] == "chat" and "no longer allergic to peanut" in calls[0][0]


def test_followup_waits_until_a_day_after_arrival_by_default(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.delenv("FEEDBACK_DELAY_SECONDS")
    wf = Workflow(FakeTools(), FakeLLM(), str(tmp_path))
    g = wf.approve_plan(wf.start("Vi", "get me coffee", "addr", ["g4"]).id)
    wf.set_sender(g.id, "+15550005555")
    wf.mark_paid(g.id)
    texts = [m["text"] for m in wf.outbox_pop()]
    assert len(texts) == 1 and texts[0].startswith("Paid.")  # the receipt only; no "how was it?" yet
    arrive = max(i.product.arrive_by for i in g.cart.items)
    due = wf._update("followups.json", {}, lambda d: d[g.id]["due"])
    assert due == (datetime(arrive.year, arrive.month, arrive.day, tzinfo=timezone.utc) + timedelta(days=2)).timestamp()
