"""Shared data shapes. agent/, tools/ and web/ all depend on these; change them only by team agreement."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal[
    "collecting",  # profiles, guest replies and calendars in flight
    "awaiting_plan_approval",
    "shopping",
    "awaiting_payment",
    "fulfilling",
    "done",
    "stopped",  # kill switch
]


class GuestProfile(BaseModel):
    id: str
    name: str
    restrictions: list[str] = []  # e.g. "vegetarian", "halal"
    allergens: list[str] = []  # e.g. "egg", "peanut"
    cuisines: list[str] = []
    contact: str | None = None


class Product(BaseModel):
    id: str
    name: str
    source: str  # which store it was pulled from
    url: str
    price: float
    pack_size: str
    ingredients: list[str]
    arrive_by: date


class CartItem(BaseModel):
    product: Product
    quantity: int = Field(default=1, ge=1)
    alternatives: list[Product] = []  # other pack sizes or sources the host can swap to
    reason: str  # why it passed every guest's restrictions


class Cart(BaseModel):
    gathering_id: str
    ship_to: str
    items: list[CartItem]

    @property
    def total(self) -> float:
        return round(sum(i.product.price * i.quantity for i in self.items), 2)


class AuditEvent(BaseModel):
    gathering_id: str
    node_id: str  # F1..F13 from docs/agent-graph.md
    time: datetime
    inputs: dict
    context_used: list[str]
    decision: str
    simulated: bool = False


class Gathering(BaseModel):
    id: str
    host: str
    request: str
    ship_to: str
    guest_ids: list[str]
    status: Status = "collecting"
    when: datetime | None = None
    menu: list[str] = []
    cart: Cart | None = None
    checkout_url: str | None = None
