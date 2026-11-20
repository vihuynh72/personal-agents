"""N26: prepared-food dishes as Products, read-only. Menu data comes from schema.org JSON-LD (Menu / MenuItem) on public pages.

Spike result: Bright Data refuses Uber Eats (robots.txt, no KYC), DoorDash search renders client-side with no
embedded data, and Yelp menu pages carry JSON-LD but no prices. So live retrieval is off by default
(RESTAURANTS_LIVE=1 tries Uber Eats and DoorDash search pages); the committed seed in product_cache/ is a labelled SAMPLE.
"""
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import quote_plus

from agent import products as store
from contracts.models import Product

log = logging.getLogger(__name__)

# (platform, public search page); GET only, never signed in, never a cart or a form
SOURCES = {
    "Uber Eats": "https://www.ubereats.com/search?q={q}",
    "DoorDash": "https://www.doordash.com/search/store/{q}/",
}
LD = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I)
LEAD = re.compile(r"^(?:\w+\s+)?(?:topped\s+)?(?:with|w/)\s+", re.I)  # "served with", "prepared w/", "topped with"
SPLIT = re.compile(r",|;|\band\b|\bw/", re.I)


def _name(node: dict) -> str:
    return str(node.get("name") or "").strip()


def _walk(node, restaurant: str = ""):
    """Yield (restaurant, MenuItem dict) for every MenuItem nested anywhere in a JSON-LD value."""
    if isinstance(node, list):
        for n in node:
            yield from _walk(n, restaurant)
    elif isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "Restaurant" in kinds or "Menu" in kinds:
            restaurant = re.sub(r"\s+Menu$", "", _name(node)) or restaurant
        if "MenuItem" in kinds:
            yield restaurant, node
        for v in node.values():
            if isinstance(v, (dict, list)):
                yield from _walk(v, restaurant)


def _price(item: dict) -> float | None:
    offers = item.get("offers") or {}
    for o in offers if isinstance(offers, list) else [offers]:
        try:
            return float(str(o.get("price")).replace("$", "").replace(",", ""))
        except (AttributeError, ValueError):
            continue
    return None


def dish_ingredients(description: str) -> list[str]:
    """Components only when the text clearly lists them ('with a, b and c'); otherwise [] so the host is asked."""
    text = LEAD.sub("", description.strip().lower()) if LEAD.match(description.strip()) else ""
    parts = [p.strip(" .") for p in SPLIT.split(text) if p.strip(" .")]
    # shortcut: 'choice of' / 'any' marks an open option, not a component; 2+ short parts is the whole test
    if len(parts) < 2 or any(len(p.split()) > 4 or re.search(r"\b(choice|any|your|option)\b", p) for p in parts):
        return []
    return parts


def parse_menu(page: str, source: str, url: str) -> list[Product]:
    out, seen = [], set()
    for m in LD.finditer(page):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for restaurant, item in _walk(data):
            price, dish = _price(item), _name(item)
            key = (restaurant, dish)
            if price is None or not dish or key in seen:  # no price, no Product: never guess one
                continue
            seen.add(key)
            h = hashlib.sha1(f"{restaurant}|{dish}".encode()).hexdigest()[:10]
            serves = re.search(r"serves\s+\d+(?:\s*-\s*\d+)?", str(item.get("description") or ""), re.I)
            out.append(Product(
                id=f"{source.lower().replace(' ', '')}-{h}", name=f"{dish} ({restaurant})" if restaurant else dish,
                source=source, url=url, price=price, pack_size=serves.group(0) if serves else "1 order",
                ingredients=dish_ingredients(str(item.get("description") or "")), arrive_by=store._arrive_by()))
    return out


def _live(query: str) -> list[Product]:
    out = []
    for source, tpl in SOURCES.items():  # at most 2 fetches per query
        url = tpl.format(q=quote_plus(query))
        try:
            out += parse_menu(store._get(url), source, url)
        except Exception as e:  # blocked, rate limited or no embedded menu: try the next source
            log.warning("%s dishes failed: %r", source, e)
    return out


def search_dishes(query: str, ship_to: str) -> list[Product]:
    slug = store._slug(query)
    for d in (store.CACHE, store.SEED):
        for name in (f"dishes-{slug}.json", f"dishes-{slug}-sample.json"):
            if (hit := store._load(d / name)) is not None:
                return hit
    # a longer request ("order dinner for six") falls back to the signal word it contains
    for word in dict.fromkeys(w.lower() for w in store.FOOD.findall(query)):
        if word != slug and (hit := store._load(store.SEED / f"dishes-{word}-sample.json")) is not None:
            return hit
    if os.environ.get("RESTAURANTS_LIVE") and os.environ.get("BRIGHTDATA_API_KEY") and os.environ.get("BRIGHTDATA_UNLOCKER_ZONE"):
        if found := _live(query):
            store.CACHE.mkdir(parents=True, exist_ok=True)
            (store.CACHE / f"dishes-{slug}.json").write_text(json.dumps([p.model_dump(mode="json") for p in found], indent=1))
            return found
    return []
