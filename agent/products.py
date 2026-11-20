"""N10: real product search (Walmart + Target) through Bright Data, with a disk cache and a committed seed cache."""
import html
import json
import logging
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote_plus

from agent.payments import StripeTools
from contracts.models import Product

log = logging.getLogger(__name__)

CACHE = Path(".data/products")  # written on every live pull
SEED = Path(__file__).parent / "product_cache"  # committed, read-only, keeps the demo offline
TOP = 4
TIMEOUT = 45  # seconds per request
CAP = 60  # seconds for a whole fan-out, so one slow page cannot hang the search
# Target's public web key, the same one target.com sends from the browser.
TARGET = "https://redsky.target.com/redsky_aggregations/v1/web/"
TARGET_KEY = "key=9f36aeafbe60771e321a7cc95a78140772ab3e96&channel=WEB&pricing_store_id=3991&visitor_id=0123456789ABCDEF0123456789ABCDEF"
# a request with one of these also gets restaurant dishes (agent/restaurants.py)
FOOD = re.compile(r"\b(dinner|lunch|catering|takeout|delivery|restaurant|pizza|tacos?|burritos?|sushi|pho|noodles?|burgers?|sandwich(?:es)?|platters?)\b", re.I)
PACK = re.compile(r"\d+(?:\.\d+)?[\s-]*(?:fl\.?\s*oz|fluid\s+ounces?|oz|ounces?|lbs?|count|ct|pack|pk|gal|qt|pt|ml|kg|g|l)\b\.?", re.I)


def _get(url: str) -> str:
    # country=us because without it Walmart sometimes answers in Spanish
    body = json.dumps({"zone": os.environ["BRIGHTDATA_UNLOCKER_ZONE"], "url": url, "format": "raw", "country": "us"}).encode()
    req = urllib.request.Request("https://api.brightdata.com/request", body, {
        "Authorization": f"Bearer {os.environ['BRIGHTDATA_API_KEY']}", "Content-Type": "application/json"})
    for _ in range(4):
        out = urllib.request.urlopen(req, timeout=TIMEOUT).read().decode()
        if not (len(out) < 300 and "rate limit" in out.lower()):  # Bright Data answers 200 with this text when busy
            return out
        time.sleep(3)
    raise RuntimeError("Bright Data rate limit")


def _next_data(page: str) -> dict:
    return json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S).group(1))


def _pack(name: str) -> str:
    m = PACK.search(name)
    return m.group(0).strip(" .") if m else ""


def split_ingredients(text: str) -> list[str]:
    """Comma split outside brackets: 'semolina (wheat), niacin.' -> ['semolina (wheat)', 'niacin']."""
    out, depth, cur = [], 0, ""
    for ch in text.lower().replace(";", ","):
        depth += (ch in "([") - (ch in ")]")
        if ch == "," and depth <= 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return [i.strip(" .\n") for i in out + [cur] if i.strip(" .\n")]


def _product(source: str, item_id: str, name: str, url: str, price: float) -> Product:
    name = html.unescape(name)
    return Product(id=f"{source.lower()}-{item_id}", name=name, source=source, url=url, price=float(price),
                   pack_size=_pack(name), ingredients=[], arrive_by=_arrive_by())


def _arrive_by() -> date:
    # shortcut: store search pages give no delivery date, so this is today + 3 days;
    # replace it with the store's delivery estimate once checkout goes through the store.
    return date.today() + timedelta(days=3)


def parse_walmart_search(page: str) -> list[tuple[Product, str]]:
    """Top non-sponsored results as (product, product page url). The team wants no ads."""
    stacks = _next_data(page)["props"]["pageProps"]["initialData"]["searchResult"]["itemStacks"]
    out, seen = [], set()
    for it in (i for s in stacks for i in s["items"]):
        if it.get("__typename") != "Product" or it.get("isSponsoredFlag") or it.get("sponsoredProduct"):
            continue
        if not it.get("price") or it["usItemId"] in seen:
            continue
        seen.add(it["usItemId"])
        url = "https://www.walmart.com" + it["canonicalUrl"].split("?")[0]
        out.append((_product("Walmart", it["usItemId"], it["name"], url, it["price"]), url))
    return out[:TOP]


def walmart_ingredients(page: str) -> list[str]:
    ing = (_next_data(page)["props"]["pageProps"]["initialData"]["data"].get("idml") or {}).get("ingredients") or {}
    return split_ingredients(((ing.get("ingredients") or {}).get("value")) or "")


def parse_target_search(page: str) -> list[tuple[Product, str]]:
    out = []
    for p in json.loads(page)["data"]["search"]["products"]:
        cur = (p.get("price") or {}).get("current_retail")
        if not cur:
            continue
        item = p["item"]
        out.append((_product("Target", p["tcin"], item["product_description"]["title"], item["enrichment"]["buy_url"], cur),
                    f"{TARGET}pdp_client_v1?{TARGET_KEY}&tcin={p['tcin']}"))
    return out[:TOP]


def target_ingredients(page: str) -> list[str]:
    prod = json.loads(page)["data"]["product"]
    for node in [prod, *(prod.get("children") or [])]:  # variants carry the list when the parent has none
        text = ((node.get("item", {}).get("enrichment") or {}).get("nutrition_facts") or {}).get("ingredients")
        if text:
            return split_ingredients(text)
    return []


# source -> (search url template, {q} is the url-quoted query, search parser, ingredient parser)
SOURCES = {
    "Walmart": ("https://www.walmart.com/search?q={q}", parse_walmart_search, walmart_ingredients),
    "Target": (f"{TARGET}plp_search_v2?{TARGET_KEY}&count=12&offset=0&platform=desktop&default_purchasability_filter=true&keyword={{q}}&page=%2Fs%2F{{q}}",
               parse_target_search, target_ingredients),
}


def _live(query: str) -> list[Product]:
    pool = ThreadPoolExecutor(12)
    try:
        q = quote_plus(query)
        searches = {s: pool.submit(_get, base.format(q=q)) for s, (base, _, _) in SOURCES.items()}
        wait(searches.values(), timeout=CAP)
        pages = []  # (product, future of its product page, ingredient parser)
        for s, (_, parse, ing) in SOURCES.items():
            try:
                pages += [(p, pool.submit(_get, url), ing) for p, url in parse(searches[s].result(timeout=0))]
            except Exception as e:  # one store down must not lose the other
                log.warning("%s search failed: %r", s, e)
        wait([f for _, f, _ in pages], timeout=CAP)
        for p, f, ing in pages:
            try:
                p.ingredients = ing(f.result(timeout=0))
            except Exception as e:  # unknown stays [], the workflow asks the host to confirm
                log.warning("%s ingredients failed: %r", p.id, e)
        return [p for p, _, _ in pages]
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _slug(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")


def _load(path: Path) -> list[Product] | None:
    if not path.exists():
        return None
    products = [Product(**d) for d in json.loads(path.read_text())]
    for p in products:
        p.arrive_by = _arrive_by()  # a cached date would be in the past
    return products


class BrightDataTools(StripeTools):
    def place_order(self, cart, source: str) -> str:
        """F13: an agent in a cloud browser checks out on our own demo store (never a real retailer)."""
        if not os.environ.get("CLOUD_ORDERING"):
            return super().place_order(cart, source)
        try:
            from agent.cloud_order import demo_card, place_order_in_cloud
            from agent.pricing import quote
            items = [{"sku": i.product.id, "name": i.product.name, "price": i.product.price, "quantity": i.quantity}
                     for i in cart.items if i.product.source == source]
            card = demo_card(cart.gathering_id, quote(cart)["total"])
            base = os.environ.get("PUBLIC_URL", "https://personal-agents-production-81468651.up.railway.app")
            res = place_order_in_cloud(base, items, "Shopper", cart.ship_to, card["number"], card["exp"], card["cvc"])
            if res.get("ok"):
                return f"{res['order_id']} (demo store, placed by cloud {res.get('path')})"
            log.warning("cloud ordering failed: %s", res.get("error"))
        except Exception as e:
            log.warning("cloud ordering failed: %r", e)
        return super().place_order(cart, source)

    def search_products(self, query: str, ship_to: str) -> list[Product]:
        found = self._search_stores(query, ship_to)
        if FOOD.search(query):
            try:
                from agent.restaurants import search_dishes  # lazy: restaurants imports this module
                found = found + search_dishes(query, ship_to)
            except Exception as e:  # dishes are a bonus, the store results stand
                log.warning("dish search failed: %r", e)
        return found

    def _search_stores(self, query: str, ship_to: str) -> list[Product]:
        # shortcut: prices come from a default store (Target store 3991, Walmart's default), not ship_to;
        # pass ship_to's zip to both stores when per-address pricing matters.
        name = _slug(query) + ".json"
        # seed before live: a committed result answers instantly, a live pull takes about a minute
        for d in (CACHE, SEED):
            if (hit := _load(d / name)) is not None:
                return hit
        if os.environ.get("BRIGHTDATA_API_KEY") and os.environ.get("BRIGHTDATA_UNLOCKER_ZONE"):
            try:
                found = _live(query)
            except Exception as e:
                log.warning("live product search failed: %r", e)
                found = []
            if found:
                CACHE.mkdir(parents=True, exist_ok=True)
                (CACHE / name).write_text(json.dumps([p.model_dump(mode="json") for p in found], indent=1))
                return found
        return super().search_products(query, ship_to)
