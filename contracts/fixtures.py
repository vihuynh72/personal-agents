"""Fake guests, catalog and tools so every owner can build before the real tools/ exist. Synthetic data only."""
from datetime import date, datetime

from .models import Cart, GuestProfile, Product

GUESTS = {
    g.id: g
    for g in [
        GuestProfile(id="g1", name="Asha", restrictions=["vegetarian"]),
        GuestProfile(id="g2", name="Ben", allergens=["egg"]),
        GuestProfile(id="g3", name="Chen", allergens=["peanut"]),
        GuestProfile(id="g4", name="Dana"),
    ]
}

_D = date(2026, 11, 27)


def _p(id, name, source, price, pack, ingredients):
    return Product(id=id, name=name, source=source, url=f"https://example.com/{id}", price=price,
                   pack_size=pack, ingredients=ingredients, arrive_by=_D)


CATALOG = [
    _p("a-pasta", "Spaghetti", "StoreA", 1.98, "16 oz", ["durum wheat semolina"]),
    _p("b-pasta", "Spaghetti", "StoreB", 2.29, "16 oz", ["durum wheat semolina"]),
    _p("a-eggpasta", "Fresh Egg Fettuccine", "StoreA", 3.49, "9 oz", ["wheat flour", "egg"]),
    _p("a-marinara", "Marinara Sauce", "StoreA", 2.75, "24 oz", ["tomato", "olive oil", "garlic", "basil"]),
    _p("b-marinara", "Marinara Sauce", "StoreB", 2.49, "24 oz", ["tomato", "olive oil", "garlic", "basil"]),
    _p("b-bolognese", "Bolognese Sauce", "StoreB", 3.99, "24 oz", ["tomato", "beef", "onion"]),
    _p("a-pesto", "Basil Pesto", "StoreA", 4.25, "6 oz", ["basil", "olive oil", "pine nut", "peanut", "parmesan"]),
    _p("a-salad", "Spring Mix Salad", "StoreA", 3.98, "5 oz", ["lettuce", "spinach"]),
    _p("b-salad", "Spring Mix Salad", "StoreB", 3.49, "11 oz", ["lettuce", "spinach"]),
    _p("a-soda6", "Sparkling Water", "StoreA", 3.98, "6-pack", ["carbonated water"]),
    _p("a-soda32", "Sparkling Water", "StoreA", 14.98, "32-pack", ["carbonated water"]),
    _p("b-bread", "Garlic Bread", "StoreB", 3.29, "10 oz", ["wheat flour", "butter", "garlic"]),
]


class FakeTools:
    """Implements contracts.tools.Tools against the data above."""

    def get_profile(self, guest_id: str) -> GuestProfile:
        return GUESTS[guest_id]

    def find_common_time(self, guest_ids: list[str], around: str) -> datetime:
        return datetime(2026, 11, 28, 19, 0)

    def search_products(self, query: str, ship_to: str) -> list[Product]:
        words = query.lower().split()
        return [p for p in CATALOG if any(w in p.name.lower() for w in words)]

    def create_checkout(self, cart: Cart) -> str:
        return f"https://example.com/checkout/{cart.gathering_id}"

    def verify_checkout(self, cart: Cart) -> bool:
        return True

    def place_order(self, cart: Cart, source: str) -> str:
        return f"sim-{source}-{cart.gathering_id}"
