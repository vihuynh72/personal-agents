import json
from pathlib import Path

import pytest

from agent import products
from agent.products import BrightDataTools

SAMPLE = json.loads((Path(__file__).parent / "products_sample.json").read_text())


def _page(data: dict) -> str:
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


def _walmart_search(items):
    return _page({"props": {"pageProps": {"initialData": {"searchResult": {"itemStacks": [{"items": items}]}}}}})


@pytest.fixture
def tools(monkeypatch, tmp_path):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    monkeypatch.setattr(products, "CACHE", tmp_path / "cache")
    return BrightDataTools()


def test_walmart_search_skips_sponsored_and_maps_fields():
    found = products.parse_walmart_search(_walmart_search(SAMPLE["wm_search"]))
    assert [p.id for p, _ in found] == ["walmart-578550306", "walmart-19621572429"]  # the 4 sponsored items are gone
    p, url = found[0]
    assert (p.source, p.price, p.pack_size, p.ingredients) == ("Walmart", 12.96, "25.9 oz", [])
    assert url == p.url and url.startswith("https://www.walmart.com/ip/") and "?" not in url


def test_walmart_ingredients_present_and_absent():
    assert products.walmart_ingredients(_page({"props": {"pageProps": {"initialData": {"data": {"idml": {"ingredients": SAMPLE["wm_ingredients"]}}}}}})) == ["coffee"]
    no_data = _page({"props": {"pageProps": {"initialData": {"data": {"idml": None}}}}})
    assert products.walmart_ingredients(no_data) == []  # unknown stays an empty list, never invented


def test_target_search_and_ingredients():
    found = products.parse_target_search(json.dumps({"data": {"search": {"products": SAMPLE["tg_search"]}}}))
    p, pdp_url = found[0]
    assert p.source == "Target" and p.id == "target-78779052" and p.price == 1.39 and p.pack_size == "16oz"
    assert "tcin=78779052" in pdp_url
    assert "&#" not in p.name  # html entities decoded
    assert products.target_ingredients(json.dumps({"data": {"product": SAMPLE["tg_pdp"]}}))[0] == "semolina (wheat)"
    assert products.target_ingredients(json.dumps({"data": {"product": {"item": {"enrichment": {}}}}})) == []


def test_split_ingredients_keeps_bracketed_commas():
    assert products.split_ingredients("SUGAR (CANE, BEET), Salt; Water.") == ["sugar (cane, beet)", "salt", "water"]


def test_cache_hit_makes_no_network_call(tools, monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_UNLOCKER_ZONE", "z")
    seed = tools.search_products("ground coffee", "x")  # seed fallback, used only to build a cache file
    products.CACHE.mkdir()
    (products.CACHE / "my-query.json").write_text(json.dumps([p.model_dump(mode="json") for p in seed[:1]]))

    def boom(*a, **k):
        raise AssertionError("network used")

    monkeypatch.setattr(products, "_get", boom)
    hit = tools.search_products("My Query!", "x")
    assert [p.id for p in hit] == [seed[0].id]


def test_seed_cache_fallback_for_ground_coffee(tools):
    found = tools.search_products("ground coffee", "1 Market St")  # no key, no .data cache
    assert len(found) >= 3
    assert all(p.price > 0 and "coffee" in p.name.lower() for p in found)


def test_live_failure_falls_back_to_seed(tools, monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_UNLOCKER_ZONE", "z")
    monkeypatch.setattr(products, "_get", lambda url: (_ for _ in ()).throw(OSError("down")))
    assert len(tools.search_products("oat milk", "x")) >= 3


def test_nothing_anywhere_uses_fake_catalog(tools):
    assert {p.name for p in tools.search_products("sparkling", "x")} == {"Sparkling Water"}
