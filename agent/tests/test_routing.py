from agent import products
from agent.chat import Chat
from agent.llm import FakeLLM
from agent.products import is_prepared
from agent.profiles import ProfileStore
from agent.restaurants import search_dishes
from agent.workflow import Workflow, route
from contracts.fixtures import CATALOG, FakeTools, _p
from contracts.models import GuestProfile

ME = "+15550002222"
KIT = _p("a-tacokit", "Street Tacos Dinner Kit", "StoreA", 6.99, "10 oz", ["corn tortilla", "spices"])


class DishTools(FakeTools):
    """FakeTools stores plus the committed sample taqueria menu (offline)."""

    def __init__(self, extra=()):
        self.extra = list(extra)

    def search_dishes(self, query, ship_to):
        return search_dishes(query, ship_to) + self.extra

    def search_products(self, query, ship_to):
        words = query.lower().split()
        stores = [p for p in CATALOG + [KIT] if any(w in p.name.lower() for w in words)]
        return stores + self.search_dishes(query, ship_to)


def _chat(tmp_path, monkeypatch, tools=None, allergens=()):
    monkeypatch.setattr(products, "CACHE", tmp_path / "cache")
    store = ProfileStore(str(tmp_path))
    store.save(GuestProfile(id=ME, name="Sam", allergens=list(allergens)))
    wf = Workflow(tools or DishTools(), FakeLLM(), str(tmp_path))
    return Chat(wf, store, FakeLLM()), wf


def _cart(wf):
    g = wf.get(wf.gatherings_of(ME)[-1])
    return g, [i.product for i in g.cart.items]


def test_route_words():
    assert route("what's for dinner")[0] == "order"
    assert route("I want to cook tacos tonight")[0] == "cook"
    assert route("get me coffee")[0] == "shop"
    assert route("order oat milk")[0] == "shop"


def test_order_in_gets_only_prepared_food(tmp_path, monkeypatch):
    c, wf = _chat(tmp_path, monkeypatch)
    reply = c.handle(ME, "order tacos for dinner")
    g, items = _cart(wf)
    assert reply.startswith("Ordering in (prepared food):") and reply.endswith("to switch.")
    assert g.fulfil == "order" and items and all(is_prepared(p) for p in items)
    assert all(p.name.endswith("(sample menu)") for p in items) and "(Sample Taqueria)" in reply
    f1 = next(e for e in wf.audit(g.id) if e.node_id == "F1")
    assert f1.inputs["fulfil"] == "order" and "tacos" in f1.inputs["fulfil_trigger"]


def test_cook_gets_no_prepared_food(tmp_path, monkeypatch):
    c, wf = _chat(tmp_path, monkeypatch)
    reply = c.handle(ME, "I want to cook tacos")
    g, items = _cart(wf)
    assert reply.startswith("Cooking (groceries):")
    assert g.fulfil == "cook" and items and not any(is_prepared(p) for p in items)


def test_peanut_dish_never_added(tmp_path, monkeypatch):
    sate = _p("s-sate", "Peanut Sate Tacos (sample menu)", "Sample Menu", 1.0, "1 order", ["chicken", "peanut"])
    c, wf = _chat(tmp_path, monkeypatch, DishTools([sate]), allergens=["peanut"])
    c.handle(ME, "order tacos for dinner")
    _, items = _cart(wf)
    assert items and not any("peanut" in ing for p in items for ing in p.ingredients)


def test_cook_instead_switches_route(tmp_path, monkeypatch):
    c, wf = _chat(tmp_path, monkeypatch)
    c.handle(ME, "order tacos for dinner")
    old = wf.gatherings_of(ME)[-1]
    reply = c.handle(ME, "cook instead")
    assert wf.get(old).status == "stopped"
    g, items = _cart(wf)
    assert g.id != old and g.fulfil == "cook" and reply.startswith("Cooking (groceries):")
    assert not any(is_prepared(p) for p in items)


def test_shop_and_group_dinner_unchanged(tmp_path, monkeypatch):
    c, wf = _chat(tmp_path, monkeypatch)
    assert c.handle(ME, "get me coffee").startswith("Here's your cart")
    assert wf.get(wf.gatherings_of(ME)[-1]).fulfil == "shop"
    g = Workflow(FakeTools(), FakeLLM(), str(tmp_path / "d")).start("host", "dinner party", "addr", ["g1", "g2"])
    assert g.mode == "dinner" and g.fulfil == "shop" and "spaghetti" in g.menu
