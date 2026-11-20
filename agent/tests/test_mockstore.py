from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.cloud_order import demo_card, place_order_http
from agent.mockstore import is_demo_card, make_router

ITEMS = [{"sku": "A1", "name": "Hummus tub", "price": 4.5, "quantity": 2},
         {"sku": "B2", "name": "Pita bread", "price": 3.0, "quantity": 1}]


def _client(tmp_path):
    app = FastAPI()
    app.include_router(make_router(tmp_path))
    return TestClient(app)


def test_full_flow_via_http(tmp_path):
    c = _client(tmp_path)
    card = demo_card("g-1", 12.0)
    res = place_order_http("http://testserver", ITEMS, "Ana", "1 Main St, SF", card["number"],
                           card["exp"], card["cvc"], data_dir=tmp_path, client=c)
    assert res["ok"] and res["path"] == "http", res
    rec = c.get(f"/demo-store/orders/{res['order_id']}").json()
    assert rec["total"] == 12.0 and len(rec["lines"]) == 2
    assert rec["card_last4"] == card["number"].replace(" ", "")[-4:]
    assert card["number"].replace(" ", "") not in (tmp_path / "demo_store" / "orders" / f"{res['order_id']}.json").read_text()
    assert "Your cart is empty" in c.get("/demo-store/cart").text


def test_empty_cart_rejected(tmp_path):
    r = _client(tmp_path).post("/demo-store/order", data={"name": "A", "address": "B",
                                                          "card_number": "4000001234567890"})
    assert r.status_code == 400 and 'id="order-id"' not in r.text


def test_non_demo_card_rejected(tmp_path):
    c = _client(tmp_path)
    res = place_order_http("http://testserver", ITEMS[:1], "Ana", "1 Main St", "4242 4242 4242 4242",
                           "12/29", "123", client=c)
    assert not res["ok"] and "402" in res["error"]


def test_product_name_escaped(tmp_path):
    r = _client(tmp_path).get("/demo-store/p/X1", params={"name": "<script>alert(1)</script>", "price": "1"})
    assert "<script>alert" not in r.text and "&lt;script&gt;" in r.text
    assert "Demo Store (not a real retailer)" in r.text


def test_demo_card_deterministic():
    a, b = demo_card("g-1", 10), demo_card("g-1", 99)
    assert a["number"] == b["number"] and a["cvc"] == b["cvc"] and a["simulated"]
    assert is_demo_card(a["number"]) and len(a["cvc"]) == 3
    assert demo_card("g-2", 10)["number"] != a["number"]
