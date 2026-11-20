"""F7 and F9 against Stripe. Everything else still comes from the fake tools until tools/ lands."""
import json
import os
import threading
from pathlib import Path

import stripe

from contracts.fixtures import FakeTools
from contracts.models import Cart

from .pricing import quote


def _line(name: str, cents: int, quantity: int = 1, description: str | None = None) -> dict:
    data = {"name": name, **({"description": description[:500]} if description else {})}
    return {"quantity": quantity, "price_data": {"currency": "usd", "unit_amount": cents, "product_data": data}}


def line_items(cart: Cart) -> list[dict]:
    """Pure: one line per product plus estimated shipping and tax, summing to quote(cart)["total"]."""
    q = quote(cart)
    out = [_line(f"{i.product.name} ({i.product.pack_size})", round(i.product.price * 100), i.quantity,
                 f"{i.product.source}. Arrives by {i.product.arrive_by}. {i.reason}") for i in cart.items]
    out += [_line(n, round(q[k] * 100)) for n, k in (("Shipping (estimated)", "shipping"), ("Estimated tax", "tax"))
            if q[k] > 0]
    return out


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
        from agent.cart_page import cart_url
        url = cart_url(cart.gathering_id)
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=line_items(cart),
            shipping_address_collection={"allowed_countries": ["US"]},
            metadata={"gathering_id": cart.gathering_id},
            success_url=url + "?paid=1",
            cancel_url=url,
        )
        self._sessions[cart.gathering_id] = session.id
        return session.url

    def _session(self, cart: Cart):
        sid = self._sessions.get(cart.gathering_id)
        return stripe.checkout.Session.retrieve(sid) if sid else None

    def is_paid(self, cart: Cart) -> bool:
        s = self._session(cart)
        return s is not None and s.payment_status == "paid"

    def shipping_address(self, cart: Cart) -> str | None:
        """The delivery address the shopper gave Stripe Checkout, one line; None if none or on any error."""
        try:
            s = self._session(cart)
            d = getattr(getattr(s, "collected_information", None), "shipping_details", None) or getattr(s, "shipping_details", None)
            a = d.address
            parts = [d.name, a.line1, a.line2, a.city, f"{a.state or ''} {a.postal_code or ''}".strip()]
            return ", ".join(p for p in parts if p) or None
        except Exception:
            return None

    def verify_checkout(self, cart: Cart) -> bool:
        s = self._session(cart)
        return s is not None and s.payment_status == "paid" and s.amount_total == round(quote(cart)["total"] * 100)
