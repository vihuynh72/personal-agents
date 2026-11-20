import threading

from agent.chat import Chat
from agent.llm import FakeLLM
from agent.pricing import quote
from agent.profiles import ProfileStore
from agent.workflow import Workflow
from contracts.fixtures import CATALOG, FakeTools

ME = "+15550002222"
CARD = {"customer": "cus_fake", "payment_method": "pm_fake", "last4": "4242", "brand": "visa"}
OFFER = "Reply AUTOPAY"


def _setup(tmp_path, tools=None):
    tools = tools or FakeTools()
    tools.card = dict(CARD)
    wf = Workflow(tools, FakeLLM(), str(tmp_path))
    c = Chat(wf, ProfileStore(str(tmp_path)), FakeLLM())
    c.handle(ME, "hi")
    c.handle(ME, "none")
    return c, wf, tools


def _pay_once(c, wf, tools):
    """A normal checkout order, paid; returns the receipt reply."""
    assert "Review and pay" in c.handle(ME, "get me coffee")
    tools.paid = True
    reply = c.handle(ME, "I paid")
    tools.paid = False
    wf.outbox_pop()
    return reply


def _latest(wf):
    return wf.get(wf.gatherings_of(ME)[-1])


def test_offer_once_and_autopay_before_payment(tmp_path):
    c, wf, tools = _setup(tmp_path)
    assert "pay once" in c.handle(ME, "autopay").lower()
    first = _pay_once(c, wf, tools)
    assert first.count(OFFER) == 1 and "$50" in first
    assert wf.card(ME)["payment_method"] == "pm_fake" and "4242424242424242" not in str(wf.card(ME))
    second = _pay_once(c, wf, tools)
    assert second.startswith("Paid.") and OFFER not in second


def test_autopay_charges_once_under_limit(tmp_path):
    c, wf, tools = _setup(tmp_path)
    _pay_once(c, wf, tools)
    assert c.handle(ME, "AutoPay").startswith("Autopay is on for orders under $50, card ending 4242")
    reply = c.handle(ME, "get me coffee")
    g = _latest(wf)
    assert reply.startswith(f"Charged ${quote(g.cart)['total']:.2f} to your card ending 4242.")
    assert "Paid. Order placed." in reply and "Review and pay" not in reply and g.checkout_url not in reply
    assert g.status == "done"
    assert tools.charges == [{"customer": "cus_fake", "payment_method": "pm_fake",
                              "amount": round(quote(g.cart)["total"] * 100)}]
    audit = wf.audit(g.id)
    assert any(e.node_id == "F7" and e.inputs.get("autopay") and "Charged" in e.decision for e in audit)
    f9 = next(e for e in audit if e.node_id == "F9")
    assert f9.inputs["payment_intent"].startswith("pi_fake") and "matches" in f9.decision
    out = wf.outbox_pop()
    assert [m for m in out if m["text"].startswith("How was")] and not [m for m in out if "Paid." in m["text"]]
    # a second call for the same gathering never charges again
    assert wf.autopay(g.id, ME)["charged"] is False and len(tools.charges) == 1


def test_concurrent_calls_charge_once(tmp_path):
    c, wf, tools = _setup(tmp_path)
    _pay_once(c, wf, tools)
    wf.set_card(ME, autopay=False)
    c.handle(ME, "get me coffee")  # awaiting_payment, not autopaid
    wf.set_card(ME, autopay=True)
    gid = _latest(wf).id
    ts = [threading.Thread(target=wf.autopay, args=(gid, ME)) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(tools.charges) == 1 and wf.get(gid).status == "done"


def test_over_limit_and_limit_change(tmp_path):
    c, wf, tools = _setup(tmp_path)
    _pay_once(c, wf, tools)
    c.handle(ME, "autopay")
    assert c.handle(ME, "autopay limit 10") == "Autopay limit is now $10."
    reply = c.handle(ME, "get me coffee")
    assert "Review and pay" in reply and "Over your $10 autopay limit." in reply
    assert _latest(wf).status == "awaiting_payment" and not getattr(tools, "charges", [])
    assert any(e.node_id == "F7" and "Autopay skipped" in e.decision for e in wf.audit(_latest(wf).id))
    c.handle(ME, "autopay limit 500")
    assert wf.card(ME)["limit"] == 200


def test_unknown_item_falls_back(tmp_path):
    class Unlabeled(FakeTools):
        def search_products(self, query, ship_to):
            return [p for p in CATALOG if p.id == "b-bulkcoffee"]  # no ingredient list: status unknown

    c, wf, tools = _setup(tmp_path, Unlabeled())
    _pay_once(c, wf, tools)
    c.handle(ME, "autopay on")
    reply = c.handle(ME, "get me coffee")
    assert "One item needs your confirmation." in reply and "Review and pay" in reply
    assert not getattr(tools, "charges", []) and _latest(wf).status == "awaiting_payment"


def test_failed_charge_falls_back(tmp_path):
    c, wf, tools = _setup(tmp_path)
    _pay_once(c, wf, tools)
    c.handle(ME, "autopay")
    tools.charge_error = "authentication_required"
    reply = c.handle(ME, "get me coffee")
    assert "Your card needs you to approve this one." in reply and "Review and pay" in reply
    assert _latest(wf).status == "awaiting_payment"


def test_autopay_off_takes_effect_next_order(tmp_path):
    c, wf, tools = _setup(tmp_path)
    _pay_once(c, wf, tools)
    c.handle(ME, "autopay")
    assert c.handle(ME, "stop autopay").startswith("Autopay is off")
    reply = c.handle(ME, "get me coffee")
    assert "Review and pay" in reply and "Not charged automatically" not in reply
    assert not getattr(tools, "charges", [])


def test_group_dinner_never_autopaid(tmp_path):
    c, wf, tools = _setup(tmp_path)
    _pay_once(c, wf, tools)
    c.handle(ME, "autopay")
    g = wf.approve_plan(wf.start("Asha", "dinner for four", "1 Main St", ["g1", "g2", "g3", "g4"]).id)
    res = wf.autopay(g.id, ME)
    assert res["charged"] is False and not getattr(tools, "charges", [])
