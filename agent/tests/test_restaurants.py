import json

import pytest

from agent import products, restaurants
from agent.products import FOOD, BrightDataTools

LD = {"@context": "https://schema.org", "@type": "Restaurant", "name": "Test Taqueria", "hasMenu": {"@type": "Menu", "hasMenuSection": [
    {"@type": "MenuSection", "name": "Mains", "hasMenuItem": [
        {"@type": "MenuItem", "name": "Carnitas Tacos", "description": "Served with pork, onion, cilantro and salsa verde", "offers": {"@type": "Offer", "price": "11.50"}},
        {"@type": "MenuItem", "name": "Super Burrito", "description": "One soft flour tortilla w/ any choice of meat", "offers": {"price": 14}},
        {"@type": "MenuItem", "name": "Family Platter", "description": "Serves 4-6. House favourite", "offers": [{"price": "$48.00"}]},
        {"@type": "MenuItem", "name": "Mystery Special", "description": "Ask your server"},  # no price: dropped
    ]}]}}
PAGE = f'<html><script type="application/ld+json">{json.dumps(LD)}</script><script type="application/ld+json">{{broken</script></html>'


def test_parse_menu_maps_dishes_and_never_invents_ingredients():
    found = restaurants.parse_menu(PAGE, "Uber Eats", "https://www.ubereats.com/store/test")
    assert [p.name for p in found] == ["Carnitas Tacos (Test Taqueria)", "Super Burrito (Test Taqueria)", "Family Platter (Test Taqueria)"]
    tacos, burrito, platter = found
    assert (tacos.source, tacos.price, tacos.pack_size, tacos.url) == ("Uber Eats", 11.5, "1 order", "https://www.ubereats.com/store/test")
    assert tacos.id.startswith("ubereats-") and tacos.id == restaurants.parse_menu(PAGE, "Uber Eats", "x")[0].id  # stable
    assert tacos.ingredients == ["pork", "onion", "cilantro", "salsa verde"]
    assert burrito.ingredients == [] and platter.ingredients == [] and platter.pack_size == "Serves 4-6"
    assert (burrito.price, platter.price) == (14.0, 48.0)


def test_ingredients_only_when_components_are_listed():
    assert restaurants.dish_ingredients("Served with rice, beans and fresh salsa") == ["rice", "beans", "fresh salsa"]
    assert restaurants.dish_ingredients("Topped w/ cheese, avocado and sour cream") == ["cheese", "avocado", "sour cream"]
    assert restaurants.dish_ingredients("A house favourite everyone loves") == []
    assert restaurants.dish_ingredients("with any choice of meat or vegetarian") == []


@pytest.fixture
def tools(monkeypatch, tmp_path):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    monkeypatch.setattr(products, "CACHE", tmp_path / "cache")
    return BrightDataTools()


def test_hook_fires_only_on_signal_words(tools, monkeypatch):
    calls = []
    monkeypatch.setattr(BrightDataTools, "_search_stores", lambda self, q, s: [])
    monkeypatch.setattr(restaurants, "search_dishes", lambda q, s: calls.append(q) or [])
    for q in ["order dinner for six", "catering for a party", "Pizza", "tacos", "sushi platter", "coffee", "oat milk", "spaghetti"]:
        tools.search_products(q, "94110")
    assert calls == ["order dinner for six", "catering for a party", "Pizza", "tacos", "sushi platter"]
    assert not FOOD.search("undeliverable pizzas")  # whole words only


def test_search_dishes_failure_does_not_break_store_results(tools, monkeypatch):
    stores = [products.Product(id="w-1", name="Tortillas", source="Walmart", url="u", price=2.0, pack_size="", ingredients=[], arrive_by="2026-11-23")]
    monkeypatch.setattr(BrightDataTools, "_search_stores", lambda self, q, s: stores)

    def boom(q, s):
        raise RuntimeError("menu site down")

    monkeypatch.setattr(restaurants, "search_dishes", boom)
    assert tools.search_products("tacos for dinner", "94110") == stores


def test_seed_sample_is_labelled_and_found_from_a_longer_request(monkeypatch, tmp_path):
    monkeypatch.setattr(products, "CACHE", tmp_path / "cache")
    monkeypatch.delenv("RESTAURANTS_LIVE", raising=False)
    found = restaurants.search_dishes("order tacos for six", "94110")
    assert found and all(p.name.endswith("(sample menu)") and p.price > 0 for p in found)
    assert restaurants.search_dishes("coffee", "94110") == []
