"""One price quote for a cart, so the cart page, the texts, the receipt and Stripe always charge the same."""
import math
import os

from contracts.models import Cart


def quote(cart: Cart) -> dict:
    """Dollars rounded to cents. Computed in integer cents, exactly as Stripe line items charge them."""
    free_over = float(os.environ.get("SHIPPING_FREE_OVER", "35.00"))
    flat = round(float(os.environ.get("SHIPPING_FLAT", "6.99")) * 100)
    rate = float(os.environ.get("TAX_RATE", "0.0938"))
    by_store: dict[str, int] = {}
    for i in cart.items:
        by_store[i.product.source] = by_store.get(i.product.source, 0) + round(i.product.price * 100) * i.quantity
    subtotal = sum(by_store.values())
    paid = sorted(s for s, c in by_store.items() if c < round(free_over * 100))
    shipping = flat * len(paid)
    # shortcut: one flat estimated rate on the subtotal; real tax depends on the address and item category
    # (most groceries are untaxed in California). Replace with Stripe Tax.
    tax = math.floor(subtotal * rate + 0.5)
    free = f"free over ${free_over:.2f} per store"
    shipping_note = (f"Estimated: ${flat / 100:.2f} flat for {', '.join(paid)} ({free})" if paid
                     else f"Estimated: free ({free})")
    return {"subtotal": subtotal / 100, "shipping": shipping / 100, "tax": tax / 100,
            "total": (subtotal + shipping + tax) / 100, "shipping_note": shipping_note,
            "tax_note": f"Estimated tax at {rate * 100:g}%; the final amount depends on the address"}
