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


def _ask(call, prompt: str, default):
    """One LLM call, retried once if the reply is not JSON of the default's type; then the default. Never loops."""
    for _ in range(2):
        try:
            out = _json(call(prompt))
            if isinstance(out, type(default)):
                return out, True
        except ValueError:  # includes json.JSONDecodeError
            pass
    return default, False


_TIMEOUT = 90  # seconds to wait for one parallel tool call


def _run_all(fns: list):
    """Fanout and join; a hung tool raises TimeoutError instead of hanging the run."""
    pool = ThreadPoolExecutor()
    try:
        futures = [pool.submit(f) for f in fns]
        return [f.result(timeout=_TIMEOUT) for f in futures]
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _matches(banned: str, ingredient: str) -> bool:
    """Whole words, case-insensitive, simple plurals: egg matches eggs but not eggplant."""
    stem = banned[:-1] if banned.endswith("s") and not banned.endswith("ss") else banned
    return bool(re.search(rf"\b{re.escape(stem)}(e?s)?\b", ingredient, re.I))


class Workflow:
    def __init__(self, tools: Tools, llm: LLM, data_dir: str = ".data"):
        self.tools, self.llm = tools, llm
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._forbidden: dict[str, list[str] | None] = {}  # None: expansion failed, products become unknown

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

        # F1 intake and router
        intake, _ = _ask(self.llm.system1,
            "Parse this request. Reply with JSON only: "
            '{"mode": "self" (buy things for myself) or "dinner" (plan a meal for a group), '
            '"kind": "home_dinner" or "restaurant", "when": "<rough time words>", "headcount": <int>}.\n'
            f"Request: {request}", {})
        if len(guest_ids) == 1 and intake.get("mode") != "dinner":
            g.mode = "self"
        self._log(audit, g, "F1", {"request": request}, [f"host:{host}"],
                  f"Mode {g.mode}. Parsed as {intake.get('kind')} around {intake.get('when')} "
                  f"for {intake.get('headcount')}.")
        self._save(g, audit)

        # fanout F2 | F3 | F4, then join; self mode skips F3 and F4
        n = len(guest_ids)
        calls = [lambda i=i: self.tools.get_profile(i) for i in guest_ids]
        if g.mode == "dinner":
            calls += [lambda i=i: self._text_guest(g, audit, i) for i in guest_ids]
            calls.append(lambda: self.tools.find_common_time(guest_ids, str(intake.get("when", ""))))
        results = _run_all(calls)
        profiles = results[:n]
        for p in profiles:
            self._log(audit, g, "F2", {"guest_id": p.id}, [f"profile:{p.id}"],
                      f"{p.name}: restrictions {p.restrictions or 'none'}, allergens {p.allergens or 'none'}.")
        if g.mode == "dinner":
            g.when = results[-1]
            self._log(audit, g, "F4", {"guest_ids": guest_ids, "around": intake.get("when")},
                      [f"calendar:{i}" for i in guest_ids], f"Everyone is free at {g.when.isoformat()}.")

        # F5 menu planning (dinner) or shopping list (self)
        facts = [{"name": p.name, "restrictions": p.restrictions, "allergens": p.allergens, "cuisines": p.cuisines}
                 for p in profiles]
        if g.mode == "self":
            prompt = ("TASK: shopping. Turn this request into a short shopping list of grocery search terms "
                      "(e.g. \"get me coffee\" -> [\"ground coffee\"]). Include only what the person asked for; "
                      "never add other items. Reply with a JSON array of strings only.\n"
                      f"Request: {request}")
        else:
            prompt = ("TASK: menu. Plan a home dinner menu that every guest can eat. Each item must be a short grocery "
                      "search term (e.g. \"spaghetti\", \"marinara sauce\"). Reply with a JSON array of strings only.\n"
                      f"Guests: {json.dumps(facts)}")
        out, ok = _ask(self.llm.system2, prompt, [])
        g.menu = [str(x).strip() for x in out if str(x).strip()][:12] or [request]  # cap: bounds F6 searches
        g.status = "awaiting_plan_approval"
        self._log(audit, g, "F5", {"guests": facts, "mode": g.mode}, [f"profile:{p.id}" for p in profiles],
                  f"Planned {'shopping list' if g.mode == 'self' else 'menu'}: {', '.join(g.menu)}."
                  + ("" if ok else " Model reply was not usable after one retry; used the request as the list."))
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
        self._forbidden = {k: v for k, v in self._forbidden.items() if v is not None}  # retry failed expansions per run

        try:
            profiles = [self.tools.get_profile(i) for i in g.guest_ids]
            items = {}  # keyed by product id: two menu items can resolve to the same product
            for m in g.menu:
                if it := self._shop(g, audit, m, profiles):
                    items.setdefault(it.product.id, it)
            items = list(items.values())
            g.cart = Cart(gathering_id=g.id, ship_to=g.ship_to, items=items)
            self._checkout(g, audit, "Built the cart")
        except Exception:
            g.status = "awaiting_plan_approval"  # nothing was bought; let the host approve again instead of sticking
            self._save(g, audit)
            raise
        g.status = "awaiting_payment"
        self._save(g, audit)
        return g

    def _check(self, product: Product, profiles: list[GuestProfile]) -> tuple[list[str], list[str]]:
        """Deterministic F6 check. Returns (conflicts as "ingredient (person)", notes that make it unknown)."""
        bad, notes = [], []
        if not product.ingredients:
            notes.append("ingredient list not available")
        for guest in profiles:
            banned = [a.lower() for a in guest.allergens]
            for r in guest.restrictions:
                f = self._forbidden_for(r)
                if f is None:
                    notes.append(f"could not check {r} ({guest.name})")
                else:
                    banned += f
            bad += [f"{i} ({guest.name})" for i in product.ingredients for b in banned if b and _matches(b, i)]
        return bad, notes

    def _forbidden_for(self, restriction: str) -> list[str] | None:
        key = restriction.lower()
        if key not in self._forbidden:
            out, ok = _ask(self.llm.system2,
                "TASK: forbidden. List the ingredients a person with this dietary restriction cannot eat. "
                "Reply with a JSON array of lowercase ingredient names only.\n"
                f"restriction: {restriction}", [])
            self._forbidden[key] = [str(x).lower() for x in out] if ok else None
        return self._forbidden[key]

    @staticmethod
    def _checks(profiles: list[GuestProfile]) -> str:
        c = ", ".join([f"no {a} ({p.name})" for p in profiles for a in p.allergens] +
                      [f"{r} ({p.name})" for p in profiles for r in p.restrictions])
        return c[:1].upper() + c[1:] if c else "No restrictions to check"

    @staticmethod
    def _unknown_reason(notes: list[str]) -> str:
        return f"Needs confirmation: {'; '.join(notes)}. Not confirmed safe."

    def _shop(self, g: Gathering, audit: list[AuditEvent], item: str, profiles: list[GuestProfile]):
        # F6: deterministic check of every ingredient against every guest; the LLM only expands restriction names.
        found = self.tools.search_products(item, g.ship_to)
        passing, unknown, rejected, notes = [], [], {}, {}
        for p in found:
            bad, notes[p.id] = self._check(p, profiles)
            if bad:
                rejected[p.id] = bad  # conflicts are never auto-added
            elif notes[p.id]:
                unknown.append(p)
            else:
                passing.append(p)
        context = [f"product:{p.id}@{p.source}" for p in found] + [f"profile:{p.id}" for p in profiles]
        inputs = {"menu_item": item, "rejected": rejected, "unknown": [p.id for p in unknown],
                  "rule": "passing first, then unknown; cheapest first within each"}
        if not passing and not unknown:
            self._log(audit, g, "F6", inputs, context, (f"No product for {item} passed every guest; left it out." if found
                       else f"No product found for {item}; left it out."))
            return None
        passing.sort(key=lambda p: p.price)
        unknown.sort(key=lambda p: p.price)
        ranked = passing + unknown
        best = ranked[0]
        if passing:
            sources = len({p.source for p in passing})
            reason = self._checks(profiles) + \
                     f". Cheapest of {len(passing)} passing options from {sources} source{'s' * (sources > 1)}."
            status, alerts = "pass", []
        else:
            reason = self._unknown_reason(notes[best.id]) + " No option passed every check."
            status, alerts = "unknown", notes[best.id]
        self._log(audit, g, "F6", inputs, context,
                  f"Chose {best.name} ({best.pack_size}) from {best.source} at ${best.price} [{status}]. {reason}")
        return CartItem(product=best, alternatives=ranked[1:], reason=reason, status=status, alerts=alerts)

    def _checkout(self, g: Gathering, audit: list[AuditEvent], what: str) -> None:
        g.checkout_url = self.tools.create_checkout(g.cart)
        self._log(audit, g, "F7", {"items": [(i.product.id, i.quantity) for i in g.cart.items]},
                  [f"product:{i.product.id}@{i.product.source}" for i in g.cart.items],
                  f"{what}: {len(g.cart.items)} items, total ${g.cart.total}, checkout {g.checkout_url}.")

    def update_cart(self, gathering_id: str, changes: list[dict]) -> Gathering:
        g, audit = self._open(gathering_id, "awaiting_payment")
        profiles = None
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
                profiles = profiles or [self.tools.get_profile(i) for i in g.guest_ids]
                bad, notes = self._check(alt, profiles)
                if bad:  # alternatives were checked when built; only a changed profile lands here
                    item.status, item.alerts, item.reason = "alert", bad, f"Conflicts: {', '.join(bad)}."
                elif notes:
                    item.status, item.alerts, item.reason = "unknown", notes, self._unknown_reason(notes)
                else:
                    item.status, item.alerts, item.reason = "pass", [], self._checks(profiles) + ". Swapped in by the host."
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
        orders = _run_all([lambda s=s: self.tools.place_order(g.cart, s) for s in sources])
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
