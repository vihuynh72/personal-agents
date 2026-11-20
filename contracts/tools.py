"""What agent/ calls and tools/ implements. All deterministic; no LLM behind these."""
from datetime import datetime
from typing import Protocol

from .models import Cart, GuestProfile, Product


class Tools(Protocol):
    def get_profile(self, guest_id: str) -> GuestProfile: ...  # F2

    def find_common_time(self, guest_ids: list[str], around: str) -> datetime: ...  # F4

    def search_products(self, query: str, ship_to: str) -> list[Product]:  # F6
        """Results from at least two sources, with full ingredient lists."""
        ...

    def create_checkout(self, cart: Cart) -> str:  # F7
        """Return a Stripe checkout URL."""
        ...

    def verify_checkout(self, cart: Cart) -> bool: ...  # F9

    def place_order(self, cart: Cart, source: str) -> str:  # F13
        """Place the order with one retailer; return an order id."""
        ...
