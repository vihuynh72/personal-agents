"""F7 and F9 against Stripe. Everything else still comes from the fake tools until tools/ lands."""
import os

import stripe

from contracts.fixtures import FakeTools
from contracts.models import Cart


class StripeTools(FakeTools):
    def __init__(self):
        key = os.environ["STRIPE_SECRET_KEY"]
        if "_test_" not in key:  # live keys take real money; this project only runs in test mode
            raise RuntimeError("STRIPE_SECRET_KEY must be a test key")
        stripe.api_key = key
        # shortcut: session ids live in memory, so a restart loses them and F9 reports unverified;
        # store the id on the gathering when the contract gets a field for it.
        self._sessions: dict[str, str] = {}

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

    def verify_checkout(self, cart: Cart) -> bool:
        sid = self._sessions.get(cart.gathering_id)
        if not sid:
            return False
        s = stripe.checkout.Session.retrieve(sid)
        return s.payment_status == "paid" and s.amount_subtotal == round(cart.total * 100)
