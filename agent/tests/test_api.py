from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from agent.api import create_app
from contracts.fixtures import CATALOG
from contracts.models import AuditEvent, Cart, CartItem, Gathering


class FakeWorkflow:
    def __init__(self):
        self.g = None

    def _need(self, gid):
        if self.g is None or self.g.id != gid:
            raise KeyError(gid)
        return self.g

    def start(self, host, request, ship_to, guest_ids):
        item = CartItem(product=CATALOG[0], quantity=2, reason="no allergens")  # 2 x 1.98
        self.g = Gathering(id="g-1", host=host, request=request, ship_to=ship_to, guest_ids=guest_ids,
                           cart=Cart(gathering_id="g-1", ship_to=ship_to, items=[item]))
        return self.g

    def get(self, gid):
        return self._need(gid)

    def approve_plan(self, gid):
        g = self._need(gid)
        if g.status == "stopped":
            raise ValueError("gathering is stopped")
        g.status = "shopping"
        return g

    def update_cart(self, gid, changes):
        g = self._need(gid)
        for c in changes:
            if c["product_id"] != "a-pasta":
                raise ValueError(f"unknown product {c['product_id']}")
            g.cart.items[0].quantity = c.get("quantity", 1)
        return g

    def mark_paid(self, gid):
        g = self._need(gid)
        g.status = "fulfilling"
        return g

    def stop(self, gid):
        g = self._need(gid)
        g.status = "stopped"
        return g

    def audit(self, gid):
        self._need(gid)
        return [AuditEvent(gathering_id=gid, node_id="F1", time=datetime(2026, 11, 20), inputs={},
                           context_used=[], decision="started")]


@pytest.fixture
def client():
    return TestClient(create_app(FakeWorkflow()))


BODY = {"host": "Vi", "request": "pasta night", "ship_to": "1 Main St", "guest_ids": ["g1", "g2"]}


def test_happy_path(client):
    assert client.get("/health").json() == {"ok": True}
    r = client.post("/gatherings", json=BODY)
    assert r.status_code == 200 and r.json()["id"] == "g-1"
    assert client.get("/gatherings/g-1").json()["host"] == "Vi"
    assert client.post("/gatherings/g-1/approve").json()["status"] == "shopping"
    r = client.patch("/gatherings/g-1/cart", json={"changes": [{"product_id": "a-pasta", "quantity": 3}]})
    assert r.json()["cart"]["items"][0]["quantity"] == 3
    assert client.post("/gatherings/g-1/paid").json()["status"] == "fulfilling"
    assert client.get("/gatherings/g-1/audit").json()[0]["node_id"] == "F1"
    assert client.post("/gatherings/g-1/stop").json()["status"] == "stopped"


def test_cart_total_in_json(client):
    assert client.post("/gatherings", json=BODY).json()["cart"]["total"] == 3.96
    r = client.patch("/gatherings/g-1/cart", json={"changes": [{"product_id": "a-pasta", "quantity": 3}]})
    assert r.json()["cart"]["total"] == 5.94


def test_cors_open(client):
    r = client.get("/health", headers={"Origin": "http://example.com"})
    assert r.headers["access-control-allow-origin"] == "*"


@pytest.mark.parametrize("method,path", [
    ("get", "/gatherings/nope"),
    ("post", "/gatherings/nope/approve"),
    ("post", "/gatherings/nope/paid"),
    ("post", "/gatherings/nope/stop"),
    ("get", "/gatherings/nope/audit"),
])
def test_unknown_id_404(client, method, path):
    client.post("/gatherings", json=BODY)
    assert getattr(client, method)(path).status_code == 404


def test_unknown_id_404_on_cart(client):
    r = client.patch("/gatherings/nope/cart", json={"changes": []})
    assert r.status_code == 404


def test_value_error_409(client):
    client.post("/gatherings", json=BODY)
    r = client.patch("/gatherings/g-1/cart", json={"changes": [{"product_id": "zzz", "quantity": 1}]})
    assert r.status_code == 409 and "unknown product zzz" in r.json()["detail"]
    client.post("/gatherings/g-1/stop")
    r = client.post("/gatherings/g-1/approve")
    assert r.status_code == 409 and r.json()["detail"] == "gathering is stopped"
