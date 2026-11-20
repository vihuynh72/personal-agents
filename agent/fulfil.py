"""Put one product in a retailer cart as a guest, via a remote CDP browser (Bright Data Browser API).

Hard limits: guest only, never types personal/payment data, never goes past the cart page,
never tries to solve or bypass a CAPTCHA / login wall (it stops and reports what it saw).
"""

import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

SHOT_DIR = Path(".data/fulfil")
TOTAL_S = 110  # whole-run budget, under the 120 s cap
STEP_MS = 20_000

STORES = {
    "walmart.com": ("Walmart", "https://www.walmart.com/cart"),
    "target.com": ("Target", "https://www.target.com/cart"),
}
BLOCK_PATTERNS = re.compile(
    r"verify you are human|are you a (human|robot)|robot or human|press (&|and) hold|captcha|"
    r"unusual traffic|access denied|px-captcha|pardon our interruption",
    re.I,
)
EMPTY_CART = re.compile(r"cart is empty|no items in (your )?cart", re.I)
ADD_SELECTORS = [
    '[data-test="shippingButton"]',  # Target
    '[data-test="orderPickupButton"]',
    'button[data-automation-id="atc"]',  # Walmart
    'button:has-text("Add to cart")',
    'button:has-text("Add")',
]


def detect_store(url: str) -> tuple[str, str] | None:
    """(store name, cart url) for a supported retailer URL, else None."""
    host = (urlparse(url).hostname or "").lower()
    for dom, val in STORES.items():
        if host == dom or host.endswith("." + dom):
            return val
    return None


def product_id(url: str) -> str:
    """Trailing numeric id in a Walmart /ip/.../123 or Target .../A-123 URL ('' if none)."""
    m = re.search(r"(?:A-)?(\d{5,})/?(?:[?#].*)?$", url)
    return m.group(1) if m else ""


def shape(ok: bool, store: str = "", cart_url: str = "", cart_text: str = "",
          screenshot: str = "", error: str | None = None) -> dict:
    return {"ok": ok, "store": store, "cart_url": cart_url, "cart_text": (cart_text or "")[:300],
            "screenshot": screenshot, "error": None if ok else (error or "unknown failure")}


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def add_to_cart(product_url: str, quantity: int = 1) -> dict:
    found = detect_store(product_url)
    if not found:
        return shape(False, error=f"unsupported store for url {product_url!r}")
    store, cart_url = found
    if quantity != 1:  # shortcut: spike only adds one unit; upgrade by clicking the qty stepper on the cart page
        return shape(False, store, cart_url, error="quantity other than 1 is not supported yet")
    wss = os.environ.get("BRIGHTDATA_BROWSER_WSS")
    if not wss:
        return shape(False, store, cart_url, error="BRIGHTDATA_BROWSER_WSS is not set")

    from playwright.sync_api import sync_playwright

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    shot = str(SHOT_DIR / f"{store.lower()}-{int(time.time())}.png")
    deadline = time.time() + TOTAL_S
    left = lambda: max(1_000, min(STEP_MS, int((deadline - time.time()) * 1000)))  # noqa: E731
    page = None
    step = "connect"
    seen = ""

    def snap():
        try:
            page.screenshot(path=shot, timeout=10_000)
        except Exception:
            pass

    def blocked() -> str | None:
        if page.locator('iframe[id*="captcha"], #px-captcha').count():
            return "CAPTCHA iframe present (PerimeterX px-captcha); not attempting to solve"
        txt = _collapse(page.inner_text("body", timeout=5_000))
        if BLOCK_PATTERNS.search(txt) or re.search(r"/(login|signin|account/login)", page.url):
            return txt[:200] or page.url
        return None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(wss, timeout=left())
            try:
                page = browser.new_page()
                page.set_default_timeout(STEP_MS)
                step = "open product page"
                try:
                    page.goto(product_url, wait_until="domcontentloaded", timeout=left())
                except Exception as e:
                    # Bright Data sends every new page to google.com first, which interrupts the first goto;
                    # the real navigation still lands, so wait for it instead of re-issuing the goto.
                    if "interrupted by another navigation" not in str(e):
                        raise
                    page.wait_for_url(re.compile(re.escape(urlparse(product_url).hostname)), timeout=left())
                    page.wait_for_load_state("domcontentloaded", timeout=left())
                page.wait_for_timeout(3_000)
                if seen := blocked():
                    snap()
                    return shape(False, store, page.url, seen, shot, f"blocked at {step}: {seen}")
                step = "click add to cart"
                clicked = False
                for sel in ADD_SELECTORS:
                    loc = page.locator(sel).first
                    if loc.count() and loc.is_visible():
                        loc.click(timeout=left())
                        clicked = True
                        break
                if not clicked:
                    snap()
                    return shape(False, store, page.url, _collapse(page.inner_text("body"))[:300], shot,
                                 "no add-to-cart control found (out of stock, variant picker, or layout change)")
                page.wait_for_timeout(3_000)
                if seen := blocked():
                    snap()
                    return shape(False, store, page.url, seen, shot, f"blocked after {step}: {seen}")
                step = "open cart"
                page.goto(cart_url, wait_until="domcontentloaded", timeout=left())
                page.wait_for_timeout(4_000)
                if seen := blocked():
                    snap()
                    return shape(False, store, page.url, seen, shot, f"blocked at {step}: {seen}")
                try:
                    body = _collapse(page.locator("main").first.inner_text(timeout=5_000))
                except Exception:
                    body = _collapse(page.inner_text("body"))
                snap()
                pid = product_id(product_url)
                in_cart = not EMPTY_CART.search(body) and (not pid or pid in page.content())
                err = None if in_cart else f"cart page does not show the item (id {pid or '?'}); cart looks empty or different"
                return shape(in_cart, store, page.url, body, shot, err)
            except Exception:
                if page is not None:  # capture what the page showed while it is still open
                    snap()
                    try:
                        seen = blocked() or seen
                    except Exception:
                        pass
                raise
            finally:
                try:
                    page.close() if page else None
                finally:
                    browser.close()
    except Exception as e:  # timeouts, CDP drops, selector errors: report, never raise
        msg = str(e).replace(wss, "<wss>")  # the endpoint string carries credentials
        msg = re.sub(r"wss?://\S+", "<wss>", msg)[:200]
        return shape(False, store, cart_url, seen, shot if Path(shot).exists() else "",
                     f"failed at {step}: {type(e).__name__}: {msg}" + (f" | page showed: {seen}" if seen else ""))
