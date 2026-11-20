"""F7 and F9 against Stripe. Everything else still comes from the fake tools until tools/ lands."""
import json
import os
import threading
from pathlib import Path

import stripe

from contracts.fixtures import FakeTools
from contracts.models import Cart


class SessionStore:
    """gathering id -> Stripe Checkout Session id, on disk so a restart can still verify and poll."""

    _lock = threading.Lock()

    def __init__(self, data_dir: str = ".data"):
        self.path = Path(data_dir) / "stripe_sessions.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def get(self, gid: str) -> str | None:
        return self._read().get(gid)

    def __setitem__(self, gid: str, sid: str) -> None:
        with self._lock:
            d = self._read()
            d[gid] = sid
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(d))
            tmp.replace(self.path)


class StripeTools(FakeTools):
    def __init__(self, data_dir: str = ".data"):
        key = os.environ["STRIPE_SECRET_KEY"]
        if "_test_" not in key:  # live keys take real money; this project only runs in test mode
            raise RuntimeError("STRIPE_SECRET_KEY must be a test key")
        stripe.api_key = key
        self._sessions = SessionStore(data_dir)

    def create_checkout(self, cart: Cart) -> str:
        web = os.environ.get("WEB_URL", "http://localhost:3000")
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "quantity": i.quantity,
                "price_data": {
                    "currency": "usd",
                    "unit_amount": round(i.product.price * 100),
                    "product_data": {
                        "name": f"{i.product.name} ({i.product.pack_size})",
                        "description": f"{i.product.source}. Arrives by {i.product.arrive_by}. {i.reason}"[:500],
                    },
                },
            } for i in cart.items],
            shipping_address_collection={"allowed_countries": ["US"]},
            metadata={"gathering_id": cart.gathering_id},
            success_url=f"{web}/gatherings/{cart.gathering_id}?paid=1",
            cancel_url=f"{web}/gatherings/{cart.gathering_id}",
        )
        self._sessions[cart.gathering_id] = session.id
        return session.url

    def _session(self, cart: Cart):
        sid = self._sessions.get(cart.gathering_id)
        return stripe.checkout.Session.retrieve(sid) if sid else None

    def is_paid(self, cart: Cart) -> bool:
        s = self._session(cart)
        return s is not None and s.payment_status == "paid"

    def verify_checkout(self, cart: Cart) -> bool:
        s = self._session(cart)
        return s is not None and s.payment_status == "paid" and s.amount_subtotal == round(cart.total * 100)
