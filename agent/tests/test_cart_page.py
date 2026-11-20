from datetime import date

import pytest
from fastapi.testclient import TestClient

from agent.api import create_app
from agent.chat import Chat
from agent.llm import FakeLLM
from agent.payments import line_items
from agent.pricing import quote
from agent.profiles import ProfileStore
from agent.workflow import Workflow
from contracts.fixtures import FakeTools
from contracts.models import Cart, CartItem, Product

EVIL = "<script>alert(1)</script> Coffee"


def _p(pid, price, source="Walmart", name=None):
    return Product(id=pid, name=name or pid, source=source, url=f"https://shop.example/{pid}", price=price,
                   pack_size="12 oz", ingredients=["coffee"], arrive_by=date(2026, 11, 24))


def _cart(*items):
    return Cart(gathering_id="abc", ship_to="x", items=[CartItem(product=p, quantity=q, reason="r") for p, q in items])


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("SHIPPING_FREE_OVER", "SHIPPING_FLAT", "TAX_RATE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PUBLIC_URL", "https://pa.example")


def test_quote_free_paid_two_retailers_and_rounding():
    assert quote(_cart((_p("a", 10.00), 4))) == {  # 40 >= 35: free; tax 3.752 -> 3.75
        "subtotal": 40.0, "shipping": 0.0, "tax": 3.75, "total": 43.75,
        "shipping_note": "Estimated: free (free over $35.00 per store)",
        "tax_note": "Estimated tax at 9.38%; the final amount depends on the address"}
    q = quote(_cart((_p("a", 7.99), 1)))  # tax 0.749 -> 0.75
    assert (q["shipping"], q["tax"], q["total"]) == (6.99, 0.75, 15.73) and "Walmart" in q["shipping_note"]
    q = quote(_cart((_p("a", 40.0), 1), (_p("b", 5.0, "Target"), 1)))  # Walmart free, Target pays
    assert q["shipping"] == 6.99 and "Target" in q["shipping_note"] and "Walmart" not in q["shipping_note"]
    assert quote(_cart((_p("a", 1.0), 1), (_p("b", 1.0, "Target"), 1)))["shipping"] == 13.98


def test_stripe_line_items_sum_to_quote():
    for cart in (_cart((_p("a", 7.99), 3), (_p("b", 2.49, "Target"), 1)), _cart((_p("a", 50.0), 1))):
        li = line_items(cart)
        assert sum(x["quantity"] * x["price_data"]["unit_amount"] for x in li) == round(quote(cart)["total"] * 100)
    names = [x["price_data"]["product_data"]["name"] for x in line_items(_cart((_p("a", 7.99), 1)))]
    assert names[-2:] == ["Shipping (estimated)", "Estimated tax"]


class Catalog(FakeTools):
    def search_products(self, query, ship_to):
        return [_p("wm-1", 7.99, name=EVIL), _p("tg-2", 9.49, "Target", name="Plain Coffee")]


def _setup(tmp_path):
    wf = Workflow(Catalog(), FakeLLM(), str(tmp_path))
    g = wf.approve_plan(wf.start("Vi", "get me coffee", "1 Main St", ["g3"]).id)
    return wf, TestClient(create_app(wf)), g


def test_cart_page_renders_escaped_and_updates_after_patch(tmp_path):
    wf, client, g = _setup(tmp_path)
    r = client.get(f"/cart/{g.id}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    html = r.text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt; Coffee" in html
    assert "View on Walmart" in html and "https://shop.example/wm-1" in html and "Plain Coffee" in html
    assert f"Pay ${quote(g.cart)['total']:.2f} with Stripe" in html and g.checkout_url in html
    assert client.get(f"/gatherings/{g.id}").json()["quote"] == quote(g.cart)
    client.patch(f"/gatherings/{g.id}/cart", json={"changes": [{"product_id": "wm-1", "quantity": 5}]})
    total = quote(wf.get(g.id).cart)["total"]
    assert total == 43.70 and f"Pay ${total:.2f} with Stripe" in client.get(f"/cart/{g.id}").text


def test_paid_page_has_receipt_not_button_and_unknown_is_404(tmp_path):
    wf, client, g = _setup(tmp_path)
    wf.mark_paid(g.id)
    html = client.get(f"/cart/{g.id}").text
    assert "with Stripe</a>" not in html and "sim-Walmart" in html and "1 Main St" in html
    r = client.get("/cart/000000000000")
    assert r.status_code == 404 and "Order not found" in r.text
    assert client.get("/cart/nope").status_code == 404


def test_receipt_has_total_charged_and_no_walmart_link(tmp_path):
    wf, _, g = _setup(tmp_path)
    wf.mark_paid(g.id)
    r = wf.receipt(g.id)
    assert "walmart.com" not in r and f"Charged ${quote(g.cart)['total']:.2f}." in r
    assert f"https://pa.example/cart/{g.id}" in r and len(r) <= 900 and "simulated" not in r and "demo" not in r.lower() and "Order numbers:" in r


def test_chat_reply_links_the_page_not_stripe(tmp_path):
    wf = Workflow(Catalog(), FakeLLM(), str(tmp_path))
    c = Chat(wf, ProfileStore(str(tmp_path)), FakeLLM())
    c.handle("+15550001111", "hi")
    c.handle("+15550001111", "none")
    reply = c.handle("+15550001111", "get me coffee")
    (gid,) = wf.ids("awaiting_payment")
    assert f"Review and pay: https://pa.example/cart/{gid}" in reply and "checkout.stripe.com" not in reply
    assert f"Total ${quote(wf.get(gid).cart)['total']:.2f}." in reply and f"- {EVIL}, $7.99 x1: " in reply
