import json

import pytest

from agent.llm import FakeLLM
from agent.workflow import Workflow
from contracts.fixtures import FakeTools

GUESTS = ["g1", "g2", "g3", "g4"]
BANNED = ["egg", "peanut", "beef", "chicken", "pork", "fish"]


def _wf(tmp_path, llm=None):
    return Workflow(FakeTools(), llm or FakeLLM(), data_dir=str(tmp_path))


def _to_payment(wf):
    g = wf.start("Vi", "dinner at my place Saturday for six", "1 Main St", GUESTS)
    assert g.status == "awaiting_plan_approval" and g.menu and g.when
    return wf.approve_plan(g.id)


def _item(g, name):
    return next(i for i in g.cart.items if i.product.name == name)


def test_happy_path_and_audit(tmp_path):
    wf = _wf(tmp_path)
    g = _to_payment(wf)
    assert g.status == "awaiting_payment" and g.checkout_url
    pasta = _item(g, "Spaghetti")
    assert pasta.product.id == "a-pasta"  # cheapest
    assert "No egg (Ben), no peanut (Chen), vegetarian (Asha)" in pasta.reason
    g = wf.update_cart(g.id, [{"product_id": "a-pasta", "quantity": 2}])
    g = wf.mark_paid(g.id)
    assert g.status == "done"
    nodes = {e.node_id for e in wf.audit(g.id)}
    assert {"F1", "F2", "F3", "F4", "F5", "F6", "F7", "F9", "F13"} <= nodes
    assert all(e.simulated for e in wf.audit(g.id) if e.node_id in ("F3", "F13"))
    assert {e.inputs["source"] for e in wf.audit(g.id) if e.node_id == "F13"} == {"StoreA", "StoreB"}


def test_no_banned_ingredients_and_bad_products_never_chosen(tmp_path):
    g = _to_payment(_wf(tmp_path))
    products = [p for i in g.cart.items for p in [i.product, *i.alternatives]]
    assert products
    for p in products:
        assert not any(b in ing for ing in p.ingredients for b in BANNED), p.id
    assert not {"a-eggpasta", "b-bolognese", "a-pesto"} & {p.id for p in products}


class RiskyMenuLLM(FakeLLM):
    def system2(self, prompt):
        if "TASK: menu" in prompt:
            return json.dumps(["fettuccine", "pesto", "sauce"])
        return super().system2(prompt)


def test_failing_products_are_left_out_and_audited(tmp_path):
    wf = _wf(tmp_path, RiskyMenuLLM())
    g = _to_payment(wf)
    assert [i.product.id for i in g.cart.items] == ["b-marinara"]  # bolognese rejected for beef
    f6 = [e for e in wf.audit(g.id) if e.node_id == "F6"]
    assert sum("left it out" in e.decision for e in f6) == 2
    assert any("b-bolognese" in e.inputs["rejected"] for e in f6)


def test_alternatives_quantity_and_swap(tmp_path):
    wf = _wf(tmp_path)
    g = _to_payment(wf)
    salad = _item(g, "Spring Mix Salad")
    assert salad.product.id == "b-salad" and [a.id for a in salad.alternatives] == ["a-salad"]
    total = g.cart.total
    g = wf.update_cart(g.id, [{"product_id": "b-salad", "quantity": 3}])
    assert g.cart.total == round(total + 2 * 3.49, 2)
    g = wf.update_cart(g.id, [{"product_id": "a-soda6", "swap_to": "a-soda32"}])
    assert _item(g, "Sparkling Water").product.id == "a-soda32"
    with pytest.raises(ValueError):
        wf.update_cart(g.id, [{"product_id": "a-pasta", "swap_to": "a-eggpasta"}])
    with pytest.raises(ValueError):
        wf.update_cart(g.id, [{"product_id": "a-pasta", "quantity": 0}])


def test_invalid_transitions_and_stop(tmp_path):
    wf = _wf(tmp_path)
    g = wf.start("Vi", "dinner Saturday", "1 Main St", GUESTS)
    with pytest.raises(ValueError):
        wf.mark_paid(g.id)
    with pytest.raises(KeyError):
        wf.get("000000000000")
    assert wf.stop(g.id).status == "stopped"
    for call in (wf.approve_plan, wf.mark_paid, lambda i: wf.update_cart(i, [])):
        with pytest.raises(ValueError):
            call(g.id)


def test_second_instance_resumes(tmp_path):
    g = _wf(tmp_path).start("Vi", "dinner Saturday", "1 Main St", GUESTS)
    wf2 = _wf(tmp_path)
    assert wf2.get(g.id) == g
    assert {e.node_id for e in wf2.audit(g.id)} >= {"F1", "F2", "F3", "F4", "F5"}
    assert wf2.mark_paid(wf2.approve_plan(g.id).id).status == "done"


def test_same_product_is_not_added_twice(tmp_path):
    class TwoBreads(FakeLLM):
        def system2(self, prompt):
            out = super().system2(prompt)
            return '["garlic bread", "italian bread"]' if "bread" in out else out

    w = Workflow(FakeTools(), TwoBreads(), str(tmp_path))
    g = w.approve_plan(w.start("Vi", "dinner", "addr", ["g1", "g2", "g3", "g4"]).id)
    ids = [i.product.id for i in g.cart.items]
    assert len(ids) == len(set(ids))


def test_self_mode_coffee_for_peanut_allergy(tmp_path):
    wf = _wf(tmp_path)
    g = wf.start("Vi", "get me coffee", "1 Main St", ["g3"])
    assert (g.mode, g.status, g.menu, g.when) == ("self", "awaiting_plan_approval", ["ground coffee"], None)
    g = wf.approve_plan(g.id)
    assert g.status == "awaiting_payment" and len(g.cart.items) == 1
    item = g.cart.items[0]
    assert (item.product.id, item.status, item.alerts) == ("a-coffee", "pass", [])
    assert "a-hazelcoffee" not in {p.id for p in [item.product, *item.alternatives]}
    assert [a.id for a in item.alternatives] == ["b-coffee", "b-bulkcoffee"]  # passing first, then unknown
    nodes = [e.node_id for e in wf.audit(g.id)]
    assert "F3" not in nodes and "F4" not in nodes
    f6 = next(e for e in wf.audit(g.id) if e.node_id == "F6")
    assert f6.inputs["rejected"] == {"a-hazelcoffee": ["peanut (Chen)"]}
    g = wf.update_cart(g.id, [{"product_id": "a-coffee", "swap_to": "b-bulkcoffee"}])
    swapped = g.cart.items[0]
    assert swapped.status == "unknown" and "ingredient list not available" in swapped.alerts
    assert wf.mark_paid(g.id).status == "done"


def test_unknown_only_when_nothing_passes(tmp_path, monkeypatch):
    from contracts import fixtures
    monkeypatch.setattr(fixtures, "CATALOG", [p for p in fixtures.CATALOG if p.id != "a-coffee" and p.id != "b-coffee"])
    wf = _wf(tmp_path)
    g = wf.approve_plan(wf.start("Vi", "get me coffee", "1 Main St", ["g3"]).id)
    item = g.cart.items[0]
    assert (item.product.id, item.status) == ("b-bulkcoffee", "unknown")
    assert "Needs confirmation" in item.reason and "safe" not in item.reason.replace("Not confirmed safe", "")


def test_eggplant_is_not_egg(tmp_path):
    from contracts.models import Product
    wf = _wf(tmp_path)
    p = Product(id="x", name="Baba Ganoush", source="StoreA", url="u", price=1, pack_size="8 oz",
                ingredients=["Eggplant", "tahini"], arrive_by="2026-11-27")
    ben = FakeTools().get_profile("g2")
    assert wf._check(p, [ben]) == ([], [])
    assert wf._check(p.model_copy(update={"ingredients": ["Eggs"]}), [ben])[0] == ["Eggs (Ben)"]


class GarbageListLLM(FakeLLM):
    def __init__(self):
        self.calls = 0

    def system2(self, prompt):
        if "TASK: shopping" in prompt:
            self.calls += 1
            return "sure! here is your list: coffee"
        return super().system2(prompt)


def test_garbage_shopping_list_retried_once_then_falls_back(tmp_path):
    llm = GarbageListLLM()
    g = _wf(tmp_path, llm).start("Vi", "get me coffee", "1 Main St", ["g3"])
    assert llm.calls == 2 and g.menu == ["get me coffee"] and g.status == "awaiting_plan_approval"


def test_failed_restriction_expansion_marks_unknown(tmp_path):
    class NoForbidden(FakeLLM):
        def system2(self, prompt):
            return "no" if "TASK: forbidden" in prompt else super().system2(prompt)

    wf = _wf(tmp_path, NoForbidden())
    g = wf.approve_plan(wf.start("Vi", "get me coffee", "1 Main St", ["g1"]).id)
    assert g.cart.items[0].status == "unknown"
    assert "could not check vegetarian (Asha)" in g.cart.items[0].alerts
