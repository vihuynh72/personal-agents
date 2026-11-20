"""Agent checkout against our own Demo Store (agent/mockstore.py): a remote browser
(Bright Data, over CDP) by default, plain HTTP as the fallback. Never a real retailer."""
import hashlib
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, build_opener

TOTAL_TIMEOUT_S = 110
STEP_TIMEOUT_MS = 20_000
_ORDER_ID = re.compile(r'id=["\']order-id["\'][^>]*>\s*(DS-[0-9a-f]{8})')


def demo_card(gathering_id: str, total) -> dict:
    h = hashlib.sha256(f"demo-card:{gathering_id}".encode()).hexdigest()
    digits = "".join(str(int(c, 16) % 10) for c in h)
    return {
        "number": "4000 00" + digits[:2] + " " + digits[2:6] + " " + digits[6:10],
        "exp": "12/29",
        "cvc": digits[10:13],
        "limit": total,
        "simulated": True,
        "label": "Simulated single-use card for the Demo Store. Not a real card.",
    }


class _Steps:
    def __init__(self):
        self.t0, self.items = time.monotonic(), []

    def add(self, text: str):
        self.items.append(f"{time.monotonic() - self.t0:5.1f}s {text}")


def _product_path(item) -> str:
    return f"/demo-store/p/{item['sku']}?" + urlencode({"name": item["name"], "price": item["price"]})


class _UrllibClient:
    """Minimal get/post client with a cookie jar; follows the store's 303 redirects."""

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def _open(self, path, data=None):
        class R: ...
        r = R()
        try:
            with self.opener.open(self.base + path, data=data, timeout=20) as resp:
                r.status_code, r.text = resp.status, resp.read().decode("utf-8", "replace")
        except HTTPError as e:
            r.status_code, r.text = e.code, e.read().decode("utf-8", "replace")
        return r

    def get(self, path):
        return self._open(path)

    def post(self, path, data):
        return self._open(path, urlencode(data).encode())


def place_order_http(base_url, items, ship_name, ship_to, card_number, card_exp, card_cvc,
                     data_dir=".data", client=None) -> dict:
    steps = _Steps()
    try:
        c = client or _UrllibClient(base_url)
        for it in items:
            r = c.get(_product_path(it))
            if r.status_code != 200:
                raise RuntimeError(f"product page {it['sku']}: HTTP {r.status_code}")
            r = c.post("/demo-store/cart/add", data={"sku": it["sku"], "name": it["name"],
                                                "price": it["price"], "quantity": it["quantity"]})
            if r.status_code != 200:
                raise RuntimeError(f"add to cart {it['sku']}: HTTP {r.status_code}")
            steps.add(f"added {it['quantity']} x {it['name']}")
        c.get("/demo-store/cart")
        steps.add("opened cart")
        c.get("/demo-store/checkout")
        steps.add("opened checkout")
        r = c.post("/demo-store/order", data={"name": ship_name, "address": ship_to, "card_number": card_number,
                                         "card_exp": card_exp, "card_cvc": card_cvc})
        m = _ORDER_ID.search(r.text)
        if r.status_code != 200 or not m:
            raise RuntimeError(f"place order: HTTP {r.status_code}")
        steps.add(f"order placed {m.group(1)}")
        return {"ok": True, "path": "http", "order_id": m.group(1), "screenshot": None,
                "steps": steps.items, "error": None}
    except Exception as e:  # never raise to the caller
        return {"ok": False, "path": "http", "order_id": None, "screenshot": None,
                "steps": steps.items, "error": str(e)[:300]}


def _browser_checkout(wss, base_url, items, ship_name, ship_to, card_number, card_exp, card_cvc, data_dir) -> dict:
    from playwright.sync_api import sync_playwright

    steps, base = _Steps(), base_url.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(wss, timeout=30_000)
        steps.add("connected to remote browser")
        page = None
        try:
            page = browser.new_page()
            page.set_default_timeout(STEP_TIMEOUT_MS)
            for it in items:
                page.goto(base + _product_path(it))
                page.fill("#quantity", str(it["quantity"]))
                page.click("#add-to-cart")
                page.wait_for_url("**/demo-store/cart")
                steps.add(f"added {it['quantity']} x {it['name']}")
            page.click("#checkout")
            page.wait_for_selector("#place-order")
            steps.add("opened checkout")
            page.fill("#name", ship_name)
            page.fill("#address", ship_to)
            page.fill("#card-number", card_number)
            page.fill("#card-exp", card_exp)
            page.fill("#card-cvc", card_cvc)
            steps.add("filled shipping and simulated card")
            page.click("#place-order")
            order_id = page.text_content("#order-id").strip()
            steps.add(f"order placed {order_id}")
            out = Path(data_dir) / "orders"
            out.mkdir(parents=True, exist_ok=True)
            shot = str(out / f"{order_id}.png")
            page.screenshot(path=shot, full_page=True)
            steps.add("saved confirmation screenshot")
            return {"ok": True, "path": "browser", "order_id": order_id, "screenshot": shot,
                    "steps": steps.items, "error": None}
        finally:
            if page:
                page.close()
            browser.close()


def place_order_in_cloud(base_url, items, ship_name, ship_to, card_number, card_exp, card_cvc,
                         data_dir=".data") -> dict:
    args = (base_url, items, ship_name, ship_to, card_number, card_exp, card_cvc)
    wss = os.environ.get("BRIGHTDATA_BROWSER_WSS")
    browser_error = "BRIGHTDATA_BROWSER_WSS not set"
    if wss:
        # Own thread: Playwright's sync API refuses to run inside an asyncio loop (FastAPI).
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            return pool.submit(_browser_checkout, wss, *args, data_dir).result(timeout=TOTAL_TIMEOUT_S)
        except Exception as e:
            browser_error = f"browser path failed: {type(e).__name__}: {str(e)[:200]}"
        finally:
            pool.shutdown(wait=False)
    res = place_order_http(*args, data_dir=data_dir)
    res["steps"].insert(0, f"fallback to http ({browser_error})")
    return res
