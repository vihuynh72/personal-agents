"""Master agent: runs the F1..F13 graph from docs/agent-graph.md, persists state, writes the audit trail (F10)."""
import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from contracts.models import AuditEvent, Cart, CartItem, Gathering, GuestProfile, Product
from contracts.tools import Tools

from .llm import LLM


def _json(text: str):
    """Parse the first JSON object or array in an LLM reply (tolerates code fences and prose)."""
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    if not m:
        raise ValueError(f"no JSON in LLM reply: {text[:200]}")
    return json.loads(m.group(0))


class Workflow:
    def __init__(self, tools: Tools, llm: LLM, data_dir: str = ".data"):
        self.tools, self.llm = tools, llm
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._forbidden: dict[str, list[str]] = {}

    # ---- persistence (F10 storage) ----

    def _path(self, gid: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", gid):  # ids come over HTTP; never let them form a path
            raise KeyError(gid)
        return self.dir / f"{gid}.json"

    def _load(self, gid: str) -> tuple[Gathering, list[AuditEvent]]:
        p = self._path(gid)
        if not p.exists():
            raise KeyError(gid)
        d = json.loads(p.read_text())
        return Gathering(**d["gathering"]), [AuditEvent(**e) for e in d["audit"]]

    def _save(self, g: Gathering, audit: list[AuditEvent]) -> None:
        tmp = self._path(g.id).with_suffix(".tmp")
        tmp.write_text(json.dumps({"gathering": g.model_dump(mode="json"),
                                   "audit": [e.model_dump(mode="json") for e in audit]}))
        tmp.replace(self._path(g.id))

    @staticmethod
    def _log(audit, g, node, inputs, context, decision, simulated=False) -> None:
        audit.append(AuditEvent(gathering_id=g.id, node_id=node, time=datetime.now(timezone.utc),
                                inputs=inputs, context_used=context, decision=decision, simulated=simulated))

    def _open(self, gid: str, *allowed: str) -> tuple[Gathering, list[AuditEvent]]:
        g, audit = self._load(gid)
        if g.status == "stopped":
            raise ValueError(f"gathering {gid} is stopped")
        if g.status not in allowed:
            raise ValueError(f"gathering {gid} is {g.status}, expected {' or '.join(allowed)}")
        return g, audit

    # ---- public API ----

    def get(self, gathering_id: str) -> Gathering:
        return self._load(gathering_id)[0]

    def audit(self, gathering_id: str) -> list[AuditEvent]:
        return self._load(gathering_id)[1]

    def start(self, host: str, request: str, ship_to: str, guest_ids: list[str]) -> Gathering:
        g = Gathering(id=uuid.uuid4().hex[:12], host=host, request=request, ship_to=ship_to, guest_ids=guest_ids)
        audit: list[AuditEvent] = []

        # F1 intake
        intake = _json(self.llm.system1(
            "Parse this dinner request. Reply with JSON only: "
            '{"kind": "home_dinner" or "restaurant", "when": "<rough time words>", "headcount": <int>}.\n'
            f"Request: {request}"))
        self._log(audit, g, "F1", {"request": request}, [f"host:{host}"],
                  f"Parsed as {intake.get('kind')} around {intake.get('when')} for {intake.get('headcount')}.")
        self._save(g, audit)

        # fanout F2 | F3 | F4, then join
        with ThreadPoolExecutor() as pool:
            f_profiles = [pool.submit(self.tools.get_profile, gid) for gid in guest_ids]
            f_texts = [pool.submit(self._text_guest, g, audit, gid) for gid in guest_ids]
            f_when = pool.submit(self.tools.find_common_time, guest_ids, str(intake.get("when", "")))
            profiles = [f.result() for f in f_profiles]
            for f in f_texts:
                f.result()
            g.when = f_when.result()
        for p in profiles:
            self._log(audit, g, "F2", {"guest_id": p.id}, [f"profile:{p.id}"],
                      f"{p.name}: restrictions {p.restrictions or 'none'}, allergens {p.allergens or 'none'}.")
        self._log(audit, g, "F4", {"guest_ids": guest_ids, "around": intake.get("when")},
                  [f"calendar:{i}" for i in guest_ids], f"Everyone is free at {g.when.isoformat()}.")

        # F5 menu planning
        facts = [{"name": p.name, "restrictions": p.restrictions, "allergens": p.allergens, "cuisines": p.cuisines}
                 for p in profiles]
        g.menu = [str(x) for x in _json(self.llm.system2(
            "TASK: menu. Plan a home dinner menu that every guest can eat. Each item must be a short grocery "
            "search term (e.g. \"spaghetti\", \"marinara sauce\"). Reply with a JSON array of strings only.\n"
            f"Guests: {json.dumps(facts)}"))]
        g.status = "awaiting_plan_approval"
        self._log(audit, g, "F5", {"guests": facts}, [f"profile:{p.id}" for p in profiles],
                  f"Planned menu: {', '.join(g.menu)}.")
        self._save(g, audit)
        return g

    def _text_guest(self, g: Gathering, audit: list[AuditEvent], guest_id: str) -> None:
        # F3: no messaging channel yet (Photon later); record what would be sent.
        self._log(audit, g, "F3", {"guest_id": guest_id}, [f"guest:{guest_id}"],
                  f"Would text guest {guest_id} an invitation and ask for missing dietary facts.", simulated=True)

    def approve_plan(self, gathering_id: str) -> Gathering:
        g, audit = self._open(gathering_id, "awaiting_plan_approval")
        self._log(audit, g, "F8", {"gate": "plan"}, [f"menu:{m}" for m in g.menu], "Host approved the plan.")
        g.status = "shopping"
        self._save(g, audit)

        profiles = [self.tools.get_profile(i) for i in g.guest_ids]
        items = {}  # keyed by product id: two menu items can resolve to the same product
        for m in g.menu:
            if it := self._shop(g, audit, m, profiles):
                items.setdefault(it.product.id, it)
        items = list(items.values())
        g.cart = Cart(gathering_id=g.id, ship_to=g.ship_to, items=items)
        self._checkout(g, audit, "Built the cart")
        g.status = "awaiting_payment"
        self._save(g, audit)
        return g

    def _violations(self, product: Product, guest: GuestProfile) -> list[str]:
        banned = [a.lower() for a in guest.allergens]
        for r in guest.restrictions:
            banned += self._forbidden_for(r)
        return [f"{i} ({guest.name})" for i in product.ingredients for b in banned if b and b in i.lower()]

    def _forbidden_for(self, restriction: str) -> list[str]:
        key = restriction.lower()
        if key not in self._forbidden:
            self._forbidden[key] = [str(x).lower() for x in _json(self.llm.system2(
                "TASK: forbidden. List the ingredients a person with this dietary restriction cannot eat. "
                "Reply with a JSON array of lowercase ingredient names only.\n"
                f"restriction: {restriction}"))]
        return self._forbidden[key]

    def _shop(self, g: Gathering, audit: list[AuditEvent], item: str, profiles: list[GuestProfile]):
        # F6: deterministic check of every ingredient against every guest; the LLM only expands restriction names.
        found = self.tools.search_products(item, g.ship_to)
        passing, rejected = [], {}
        for p in found:
            bad = [v for guest in profiles for v in self._violations(p, guest)]
            if bad:
                rejected[p.id] = bad
            else:
                passing.append(p)
        context = [f"product:{p.id}@{p.source}" for p in found] + [f"profile:{p.id}" for p in profiles]
        inputs = {"menu_item": item, "rejected": rejected}
        if not passing:
            self._log(audit, g, "F6", inputs, context, (f"No product for {item} passed every guest; left it out." if found
                       else f"No product found for {item}; left it out."))
            return None
        passing.sort(key=lambda p: p.price)
        best = passing[0]
        checks = [f"no {a} ({p.name})" for p in profiles for a in p.allergens] + \
                 [f"{r} ({p.name})" for p in profiles for r in p.restrictions]
        sources = len({p.source for p in passing})
        checked = ", ".join(checks)
        reason = (checked[:1].upper() + checked[1:] if checks else "No restrictions to check") + \
                 f". Cheapest of {len(passing)} passing options from {sources} source{'s' * (sources > 1)}."
        self._log(audit, g, "F6", inputs, context,
                  f"Chose {best.name} ({best.pack_size}) from {best.source} at ${best.price}. {reason}")
        return CartItem(product=best, alternatives=passing[1:], reason=reason)

    def _checkout(self, g: Gathering, audit: list[AuditEvent], what: str) -> None:
        g.checkout_url = self.tools.create_checkout(g.cart)
        self._log(audit, g, "F7", {"items": [(i.product.id, i.quantity) for i in g.cart.items]},
                  [f"product:{i.product.id}@{i.product.source}" for i in g.cart.items],
                  f"{what}: {len(g.cart.items)} items, total ${g.cart.total}, checkout {g.checkout_url}.")

    def update_cart(self, gathering_id: str, changes: list[dict]) -> Gathering:
        g, audit = self._open(gathering_id, "awaiting_payment")
        for c in changes:
            item = next((i for i in g.cart.items if i.product.id == c.get("product_id")), None)
            if item is None:
                raise ValueError(f"no cart item {c.get('product_id')}")
            if "swap_to" in c:
                alt = next((a for a in item.alternatives if a.id == c["swap_to"]), None)
                if alt is None:
                    raise ValueError(f"{c['swap_to']} is not an alternative for {item.product.id}")
                item.alternatives = [a for a in item.alternatives if a.id != alt.id] + [item.product]
                item.product = alt
            if "quantity" in c:
                q = c["quantity"]
                if not isinstance(q, int) or isinstance(q, bool) or q < 1:
                    raise ValueError(f"quantity must be an integer >= 1, got {q!r}")
                item.quantity = q
        self._log(audit, g, "F8", {"changes": changes}, [], "Host edited the cart.")
        self._checkout(g, audit, "Rebuilt the checkout")
        self._save(g, audit)
        return g

    def mark_paid(self, gathering_id: str) -> Gathering:
        g, audit = self._open(gathering_id, "awaiting_payment")
        g.status = "fulfilling"
        self._save(g, audit)

        # F13 fanout: one simulated retailer order per source
        sources = sorted({i.product.source for i in g.cart.items})
        with ThreadPoolExecutor() as pool:
            orders = list(pool.map(lambda s: self.tools.place_order(g.cart, s), sources))
        for s, oid in zip(sources, orders):
            self._log(audit, g, "F13", {"source": s},
                      [f"product:{i.product.id}" for i in g.cart.items if i.product.source == s],
                      f"Placed order {oid} with {s}.", simulated=True)

        ok = self.tools.verify_checkout(g.cart)  # F9
        self._log(audit, g, "F9", {"checkout_url": g.checkout_url}, [f"cart_total:{g.cart.total}"],
                  "Checkout session matches the cart." if ok else "Checkout session does NOT match the cart.")
        self._log(audit, g, "F11", {}, [f"profile:{i}" for i in g.guest_ids],
                  "Feedback will be recorded into each profile after the dinner.")
        g.status = "done"
        self._save(g, audit)
        return g

    def stop(self, gathering_id: str) -> Gathering:
        g, audit = self._load(gathering_id)
        prev = g.status
        g.status = "stopped"
        self._log(audit, g, "F8", {"previous_status": prev}, [], "Kill switch: stopped and handed control to the host.")
        self._save(g, audit)
        return g
