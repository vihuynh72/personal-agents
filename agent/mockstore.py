"""Demo Store: a tiny fake retailer served by our backend, so an agent can run a
real browser checkout end to end without touching any real retailer."""
import html
import json
import math
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

HEADING = "Demo Store (not a real retailer)"
COOKIE = "ds_cart"
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def is_demo_card(number: str) -> bool:
    digits = re.sub(r"[\s-]", "", number or "")
    return len(digits) == 16 and digits.isdigit() and digits.startswith("400000")


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title></head>"
        f"<body><h1>{HEADING}</h1><p><em>This is our own demo shop. No real goods are sold.</em></p>"
        f"{body}</body></html>",
        status_code=status,
    )


async def _form(request: Request) -> dict:
    # Parsed by hand: python-multipart is not a dependency.
    raw = (await request.body()).decode("utf-8", "replace")
    return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}


def make_router(data_dir) -> APIRouter:
    root = Path(data_dir) / "demo_store"
    carts, orders = root / "carts", root / "orders"
    router = APIRouter(prefix="/demo-store")

    def cart_id(request: Request) -> str | None:
        cid = request.cookies.get(COOKIE)
        return cid if cid and _ID.match(cid) else None

    def load_cart(cid: str | None) -> list:
        path = carts / f"{cid}.json"
        return json.loads(path.read_text()) if cid and path.exists() else []

    def save_cart(cid: str, lines: list) -> None:
        carts.mkdir(parents=True, exist_ok=True)
        (carts / f"{cid}.json").write_text(json.dumps(lines))

    @router.get("/p/{sku}")
    def product(sku: str, name: str = "", price: str = "0"):
        s, n, p = html.escape(sku), html.escape(name or sku), html.escape(price)
        return _page(name or sku, f"""
<h2 id="product-name">{n}</h2><p>Price: $<span id="price">{p}</span></p>
<form method="post" action="/demo-store/cart/add">
<input type="hidden" name="sku" value="{s}"><input type="hidden" name="name" value="{n}">
<input type="hidden" name="price" value="{p}">
<label>Quantity <input id="quantity" name="quantity" type="number" min="1" max="99" value="1"></label>
<button id="add-to-cart" type="submit">Add to cart</button></form>""")

    @router.post("/cart/add")
    async def cart_add(request: Request):
        f = await _form(request)
        try:
            price, qty = float(f.get("price", "")), int(f.get("quantity", "1"))
        except ValueError:
            return _page("Error", "<p id='error'>Bad price or quantity.</p>", 400)
        if not math.isfinite(price) or price < 0 or not 1 <= qty <= 99 or not f.get("sku"):
            return _page("Error", "<p id='error'>Bad item.</p>", 400)
        cid = cart_id(request) or secrets.token_hex(8)
        lines = load_cart(cid)
        lines.append({"sku": f["sku"][:64], "name": f.get("name", "")[:200], "price": round(price, 2), "quantity": qty})
        save_cart(cid, lines)
        resp = RedirectResponse("/demo-store/cart", status_code=303)
        resp.set_cookie(COOKIE, cid, path="/demo-store", httponly=True, samesite="lax")
        return resp

    @router.get("/cart")
    def cart(request: Request):
        lines = load_cart(cart_id(request))
        rows = "".join(
            f"<li class='line'>{html.escape(l['name'])} x {l['quantity']} @ ${l['price']:.2f}</li>" for l in lines
        ) or "<li>Your cart is empty.</li>"
        total = sum(l["price"] * l["quantity"] for l in lines)
        return _page("Cart", f"<h2>Cart</h2><ul>{rows}</ul><p>Total: $<span id='total'>{total:.2f}</span></p>"
                             "<a id='checkout' href='/demo-store/checkout'>Checkout</a>")

    @router.get("/checkout")
    def checkout():
        return _page("Checkout", """<h2>Checkout</h2>
<form method="post" action="/demo-store/order">
<label>Name <input id="name" name="name"></label><br>
<label>Shipping address <input id="address" name="address"></label><br>
<label>Card number <input id="card-number" name="card_number" autocomplete="off"></label><br>
<label>Expiry <input id="card-exp" name="card_exp" placeholder="MM/YY"></label><br>
<label>CVC <input id="card-cvc" name="card_cvc" autocomplete="off"></label><br>
<button id="place-order" type="submit">Place order</button></form>""")

    @router.post("/order")
    async def order(request: Request):
        f = await _form(request)
        cid = cart_id(request)
        lines = load_cart(cid)
        if not lines:
            return _page("Error", "<p id='error'>Your cart is empty.</p>", 400)
        card = re.sub(r"[\s-]", "", f.get("card_number", ""))
        if not is_demo_card(card):
            return _page("Error", "<p id='error'>Card declined: only the simulated demo card is accepted.</p>", 402)
        if not f.get("name") or not f.get("address"):
            return _page("Error", "<p id='error'>Name and shipping address are required.</p>", 400)
        rec = {
            "order_id": f"DS-{secrets.token_hex(4)}",
            "lines": lines,
            "total": round(sum(l["price"] * l["quantity"] for l in lines), 2),
            "ship_to": {"name": f["name"][:200], "address": f["address"][:500]},
            "card_last4": card[-4:],  # never store the full number
            "placed_at": datetime.now(timezone.utc).isoformat(),
        }
        orders.mkdir(parents=True, exist_ok=True)
        (orders / f"{rec['order_id']}.json").write_text(json.dumps(rec, indent=2))
        (carts / f"{cid}.json").unlink(missing_ok=True)
        return _page("Order placed", f"<h2>Thank you, order placed</h2><p>Order number: "
                                     f"<strong id='order-id'>{rec['order_id']}</strong></p>"
                                     f"<p>Total charged: ${rec['total']:.2f} to card ending {rec['card_last4']}</p>")

    @router.get("/orders/{order_id}")
    def get_order(order_id: str):
        path = orders / f"{order_id}.json"
        if not _ID.match(order_id) or not path.exists():
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(json.loads(path.read_text()))

    return router
