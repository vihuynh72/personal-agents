"""Master agent: runs the F1..F13 graph from docs/agent-graph.md, persists state, writes the audit trail (F10)."""
import json
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from contracts.models import AuditEvent, Cart, CartItem, Gathering, GuestProfile, Product
from contracts.tools import Tools

from .cart_page import cart_url
from .llm import LLM
from .pricing import quote
from .profiles import ProfileStore


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


_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(fl\.?\s*oz|oz|ounces?|lbs?|pounds?|pack|pk|count|ct)\b", re.I)
_BUDGET = re.compile(r"(?:under|below|less than|max(?:imum)?|up to|budget(?: of)?|<)\s*\$?\s*(\d+(?:\.\d+)?)", re.I)


def _size(pack: str) -> tuple[float, str] | None:
    """'11 oz' -> (11, 'oz'); '1.063 lb' -> (17.0, 'oz'); '12 fl oz' -> (12, 'fl oz'); '6-pack' -> (6, 'count')."""
    m = _SIZE.search(pack or "")
    if not m or float(m.group(1)) <= 0:
        return None
    q, u = float(m.group(1)), m.group(2).lower()
    if u.startswith("fl"):
        return q, "fl oz"
    if u.startswith(("lb", "pound")):
        return q * 16, "oz"
    return (q, "oz") if u.startswith(("oz", "ounce")) else (q, "count")


def _style(prefs: list[str]) -> list[str]:
    """Preferences that match product words; budgets are filters, and "cheapest" switches the others off."""
    if any(re.search(r"\bcheapest\b", p, re.I) for p in prefs):
        return []
    return [p for p in prefs if not _BUDGET.search(p) and re.search(r"\w", p)]


def _hits(p: Product, style: list[str]) -> list[str]:
    hay = " ".join([p.name, *p.ingredients])
    return [s for s in style if all(re.search(rf"\b{re.escape(w)}\b", hay, re.I) for w in re.findall(r"[\w'&]+", s))]


def _rank(products: list[Product], style: list[str], budget: float | None) -> tuple[list[Product], dict]:
    """Within one safety tier: in budget, then most preference hits, then unit price (unparsed sizes after), then sticker."""
    sizes = {p.id: _size(p.pack_size) for p in products}
    kinds = {s[1] for s in sizes.values() if s}
    per_unit = len(kinds) == 1  # unit prices only compare within one unit; unparsed sizes rank after known ones
    has = lambda p: per_unit and sizes[p.id] is not None
    unit = lambda p: p.price / sizes[p.id][0] if has(p) else p.price
    over = lambda p: budget is not None and p.price > budget
    ranked = sorted(products, key=lambda p: (over(p), -len(_hits(p, style)), per_unit and not has(p), unit(p), p.price))
    return ranked, {"per_unit": per_unit, "unit": kinds.pop() if per_unit else None, "price": unit, "has_unit": has,
                    "unparsed": [p.id for p in products if sizes[p.id] is None]}


# a form the shopper (or the shopping list) names -> product-name words that contradict it
_FORMS = {"ground": r"\b(instant|pods?|k-?cups?|single[- ]serve)\b",
          "whole bean": r"\b(ground|instant|pods?|k-?cups?|single[- ]serve)\b"}


def _wrong_form(item: str, p: Product) -> bool:
    return any(re.search(rf"\b{f}\b", item, re.I) and re.search(bad, p.name, re.I) for f, bad in _FORMS.items())


def _who(p: GuestProfile) -> str:
    """Display name in reasons; a chat profile saved without a name (name == phone id) reads as "you"."""
    return p.name if p.name and p.name != p.id else "you"


class Workflow:
    def __init__(self, tools: Tools, llm: LLM, data_dir: str = ".data", senso=None, profiles: ProfileStore | None = None):
        self.tools, self.llm, self.senso = tools, llm, senso  # senso: optional agent.senso.Senso; None leaves the flow unchanged
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.profiles = profiles or ProfileStore(data_dir)
        self._forbidden: dict[str, list[str] | None] = {}  # None: expansion failed, products become unknown
        self._lock = threading.RLock()  # mark_paid's check-and-set, and the small JSON files below

    def _profile(self, person_id: str) -> GuestProfile:
        """Saved profile first, then the tools (fixtures)."""
        return self.profiles.get(person_id) or self.tools.get_profile(person_id)

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

    def _update(self, name: str, default, fn):
        """Read-modify-write one small JSON file in the data dir under the lock; returns fn's result."""
        with self._lock:
            p = self.dir / "notify" / name  # subdir: the data dir root holds only gathering files
            p.parent.mkdir(exist_ok=True)
            d = json.loads(p.read_text()) if p.exists() else default
            out = fn(d)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(d))
            tmp.replace(p)
            return out

    # ---- public API ----

    def ids(self, status: str) -> list[str]:
        return [p.stem for p in self.dir.glob("*.json")
                if re.fullmatch(r"[0-9a-f]{12}", p.stem) and self.get(p.stem).status == status]

    def set_sender(self, gathering_id: str, sender: str) -> None:
        """Chat records who ordered, so the receipt can be texted back."""
        self._update("senders.json", {}, lambda d: d.__setitem__(gathering_id, sender))

    def sender(self, gathering_id: str) -> str | None:
        return self._update("senders.json", {}, lambda d: d.get(gathering_id))

    def gatherings_of(self, sender: str) -> list[str]:
        """Oldest first."""
        return self._update("senders.json", {}, lambda d: [g for g, s in d.items() if s == sender])

    def outbox_pop(self) -> list[dict]:
        """Every queued text, removed from the queue (the iMessage bot pulls GET /outbox)."""
        return self._update("outbox.json", [], lambda d: [d.pop(0) for _ in range(len(d))])

    def check_paid(self, gathering_id: str, notify: bool = True) -> Gathering | None:
        """Ask the payment tool; if paid, run fulfilment. None while unpaid."""
        g = self.get(gathering_id)
        if g.status != "awaiting_payment" or not g.cart or not self.tools.is_paid(g.cart):
            return None
        return self.mark_paid(gathering_id, notify)

    def receipt(self, gathering_id: str) -> str:
        g, audit = self._load(gathering_id)
        orders = [f"{e.inputs['source']} order {e.inputs.get('order_id')}" for e in audit
                  if e.node_id == "F13" and "source" in e.inputs]
        arrive = max(i.product.arrive_by for i in g.cart.items)
        q = quote(g.cart)
        items = ["Paid. Order placed."] + [f"- {i.product.name} x{i.quantity}, ${i.product.price * i.quantity:.2f}"
                                           for i in g.cart.items]
        tail = [f"Subtotal ${q['subtotal']:.2f}, shipping ${q['shipping']:.2f} (est.), tax ${q['tax']:.2f} (est.). "
                f"Charged ${q['total']:.2f}.",
                f"Retailers: {'; '.join(orders)}.", f"Ships to {g.ship_to}.",
                f"Estimated arrival {arrive.isoformat()}.", f"Details: {cart_url(g.id)}",
                "Note: the retailer orders and the virtual card are simulated in this demo; "
                "the Stripe payment was a test-mode payment."]
        text = "\n".join(items + tail)
        if len(text) > 900:  # keep the totals and the closing line; trim items
            t = "\n".join(tail)
            text = "\n".join(items)[:896 - len(t)] + "...\n" + t
        who = self.sender(gathering_id)
        if who and (c := self.card(who)) and not c.get("offered") and not c["autopay"]:  # the one-time opt-in offer
            self.set_card(who, offered=True)
            text += (f"\nReply AUTOPAY and I'll charge this card automatically for orders under ${c['limit']:g} "
                     "from now on.")
        return text

    # ---- autopay: per sender, only Stripe ids, brand and last four; never a card number ----

    def card(self, sender: str) -> dict | None:
        p = self.dir / "notify" / "cards.json"  # read only: an unknown sender must not create files
        with self._lock:
            return json.loads(p.read_text()).get(sender) if p.exists() else None

    def set_card(self, sender: str, **fields) -> None:
        self._update("cards.json", {}, lambda d: d.__setitem__(sender, {**d.get(sender, {}), **fields}))

    def autopay(self, gathering_id: str, sender: str) -> dict | None:
        """Charge the sender's saved card for a chat cart if autopay allows. None when autopay is off;
        else {"charged": bool, "reason": str | None, "card": dict}. The lock and the charge record mean one
        gathering is never charged twice."""
        c = self.card(sender)
        if not c or not c.get("autopay"):
            return None
        with self._lock:
            g = self.get(gathering_id)
            total = quote(g.cart)["total"] if g.cart else 0
            done = self._update("autopay_charges.json", {}, lambda d: d.get(gathering_id))
            reason = ("Already charged." if done or g.status != "awaiting_payment" else
                      "This order is not yours to autopay." if g.mode != "self" or self.sender(gathering_id) != sender else
                      "One item needs your confirmation." if any(i.status != "pass" for i in g.cart.items) else
                      f"Over your ${c['limit']:g} autopay limit." if total > c["limit"] else None)
            res = None
            if reason is None:
                res = self.tools.charge_saved(c["customer"], c["payment_method"], g.cart)
                if res.get("ok"):
                    self._update("autopay_charges.json", {}, lambda d: d.__setitem__(gathering_id, res["id"]))
                else:
                    reason = "Your card needs you to approve this one."
        card = f"{c['brand']} ending {c['last4']}"
        if reason == "Already charged.":
            # A concurrent caller lost the race. Writing an audit event here would save a stale copy of the
            # gathering over the winner's fulfilment and leave it stuck at "fulfilling".
            return {"charged": False, "reason": reason, "card": c}
        self.log_event(gathering_id, "F7", {"autopay": True, "amount": total, "limit": c["limit"], "card": card,
                                            "payment_intent": res and res.get("id"), "error": res and res.get("error")},
                       [f"card:{c['customer']}", f"cart_total:{total}"],
                       f"Charged ${total:.2f} automatically to the saved {card}, PaymentIntent {res['id']}."
                       if reason is None else f"Autopay skipped: {reason} {(res or {}).get('error') or ''}".strip())
        if reason is None:
            self.mark_paid(gathering_id, notify=False, intent={"id": res["id"], "amount": round(total * 100)})
        return {"charged": reason is None, "reason": reason, "card": c}

    def get(self, gathering_id: str) -> Gathering:
        return self._load(gathering_id)[0]

    def audit(self, gathering_id: str) -> list[AuditEvent]:
        return self._load(gathering_id)[1]

    def start(self, host: str, request: str, ship_to: str, guest_ids: list[str], mode: str | None = None) -> Gathering:
        """mode="self" forces buy-for-myself (chat); None lets F1 decide."""
        g = Gathering(id=uuid.uuid4().hex[:12], host=host, request=request, ship_to=ship_to, guest_ids=guest_ids)
        audit: list[AuditEvent] = []

        # F1 intake and router
        intake, _ = _ask(self.llm.system1,
            "Parse this request. Reply with JSON only: "
            '{"mode": "self" (buy things for myself) or "dinner" (plan a meal for a group), '
            '"kind": "home_dinner" or "restaurant", "when": "<rough time words>", "headcount": <int>}.\n'
            f"Request: {request}", {})
        if mode == "self" or (len(guest_ids) == 1 and intake.get("mode") != "dinner"):
            g.mode = "self"
        self._log(audit, g, "F1", {"request": request}, [f"host:{host}"],
                  f"Mode {g.mode}. Parsed as {intake.get('kind')} around {intake.get('when')} "
                  f"for {intake.get('headcount')}.")
        self._save(g, audit)

        # fanout F2 | F3 | F4, then join; self mode skips F3 and F4
        n = len(guest_ids)
        calls = [lambda i=i: self._profile(i) for i in guest_ids]
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
                      "(e.g. \"get me coffee\" -> [\"ground coffee\"]). Use the most common everyday form of a "
                      "product unless the shopper names one. Include only what the person asked for; never add "
                      "other items. If the request is only a vague meal (e.g. \"what's for dinner\"), propose one "
                      "simple meal of 2 to 4 grocery items the shopper can eat. Reply with a JSON array of strings only.\n"
                      f"Shopper: {json.dumps(facts)}\nRequest: {request}")
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
            profiles = [self._profile(i) for i in g.guest_ids]
            items = {}  # keyed by product id: two menu items can resolve to the same product
            for m in g.menu:
                if it := self._shop(g, audit, m, profiles):
                    items.setdefault(it.product.id, it)
            items = list(items.values())
            g.cart = Cart(gathering_id=g.id, ship_to=g.ship_to, items=items)
            if self.senso and items:
                self._senso_check(g, audit, profiles)
            if not g.cart.items:  # every candidate was rejected or removed; an empty Stripe session is an error
                self._log(audit, g, "F7", {}, [], "No item passed every check, so no checkout was created.")
                raise ValueError("nothing passed the ingredient and context checks, so there is nothing to buy")
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
                    notes.append(f"could not check {r} ({_who(guest)})")
                else:
                    banned += f
            bad += [f"{i} ({_who(guest)})" for i in product.ingredients for b in banned if b and _matches(b, i)]
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
        c = ", ".join([f"no {a} ({_who(p)})" for p in profiles for a in p.allergens] +
                      [f"{r} ({_who(p)})" for p in profiles for r in p.restrictions])
        return (c[:1].upper() + c[1:] + ", per the store's ingredient list") if c else "No restrictions to check"

    @staticmethod
    def _unknown_reason(notes: list[str]) -> str:
        return f"Needs confirmation: {'; '.join(notes)}. Not confirmed safe."

    def _shop(self, g: Gathering, audit: list[AuditEvent], item: str, profiles: list[GuestProfile]):
        # F6: deterministic check of every ingredient against every guest; the LLM only expands restriction names.
        found = self.tools.search_products(item, g.ship_to)
        wrong = [p.id for p in found if _wrong_form(item, p)]
        if len(wrong) < len(found):  # drop products that contradict the named form, unless nothing else is left
            found = [p for p in found if p.id not in wrong]
        else:
            wrong = []
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
        prefs = profiles[0].preferences if profiles else []  # the buyer's (first guest's) style only
        style = _style(prefs)
        budget = min((float(m.group(1)) for p in prefs if (m := _BUDGET.search(p))), default=None)
        inputs = {"menu_item": item, "rejected": rejected, "wrong_form": wrong, "unknown": [p.id for p in unknown],
                  "rule": "ranked by safety, then stated preferences, then unit price; passing first, then unknown; "
                          "a budget only drops passing options when one within it remains; no sponsored placement",
                  "preferences": prefs, "style_used": style, "budget": budget}
        if not passing and not unknown:
            self._log(audit, g, "F6", inputs, context, (f"No product for {item} passed every guest; left it out." if found
                       else f"No product found for {item}; left it out."))
            return None
        passing, basis = _rank(passing, style, budget)
        unknown, _ = _rank(unknown, style, None)
        ranked = passing + unknown
        inputs["price_basis"] = (f"unit price per {basis['unit']}"
                                 + (f"; unparsed pack sizes ranked after: {basis['unparsed']}" if basis["unparsed"] else "")
                                 if basis["per_unit"] else
                                 f"sticker price: pack sizes not comparable (unparsed: {basis['unparsed']})")
        best = ranked[0]
        senso_note, no_context = "", False
        if self.senso:
            ctx, text = self._senso_search(g, audit, best)  # text None: the call failed and was audited
            context += ctx
            if text is not None:
                inputs["senso"] = text
                no_context = not ctx
                senso_note = " Senso: no supporting context in Senso." if no_context else " Senso: supporting context found."
        if passing:
            sources = len({p.source for p in passing})
            hit = _hits(best, style)
            pref = (f"Matches preference: {', '.join(hit)}." if hit else
                    f"No preference matched ({', '.join(style)})." if style else
                    "Preference: cheapest." if any(re.search(r"\bcheapest\b", p, re.I) for p in prefs) else
                    f"Within budget ${budget:g}." if budget is not None else "No stated preferences.")
            if budget is not None and best.price > budget:
                pref += f" Nothing passing was under ${budget:g}."
            price = (f"${basis['price'](best):.2f}/{basis['unit']}" if basis["has_unit"](best)
                     else f"${best.price:.2f} (sticker price, pack sizes not comparable)")
            reason = self._checks(profiles) + \
                     f". {pref} {price}, best of {len(passing)} passing options from {sources} source{'s' * (sources > 1)}."
            status, alerts = "pass", []
        else:
            reason = self._unknown_reason(notes[best.id]) + " No option passed every check."
            status, alerts = "unknown", notes[best.id]
        if no_context:  # Senso answered but had nothing: never call it safe
            alert = "Senso context could not confirm this product"
            status, alerts = "unknown", alerts + [alert]
            reason = self._unknown_reason(alerts)  # never keep a "No peanut (...)" pass reason on an unknown item
        self._log(audit, g, "F6", inputs, context,
                  f"Chose {best.name} ({best.pack_size}) from {best.source} at ${best.price} [{status}]. {reason}{senso_note}")
        return CartItem(product=best, alternatives=ranked[1:], reason=reason, status=status, alerts=alerts)

    def _senso_search(self, g, audit, p: Product) -> tuple[list[str], str | None]:
        """Trusted context for one chosen product: (context_used strings, top chunk or the no-context sentence)."""
        try:
            hits = self.senso.search(f"{p.name} {', '.join(p.ingredients)}"[:500])
        except Exception as e:
            self._log(audit, g, "F10", {"senso": "search", "product": p.id}, [], f"Senso search failed: {e}. Continued without it.")
            return [], None
        ctx = [f"senso:content_id={h.get('content_id')} version={h.get('version_id')} rank={h.get('rank')} score={h.get('score')}"
               for h in hits]
        return ctx, (hits[0].get("chunk_text") or "")[:200] if hits else "no supporting context in Senso"

    def _senso_check(self, g: Gathering, audit: list[AuditEvent], profiles: list[GuestProfile]) -> None:
        """Senso fact-check of the cart's claims before checkout; one F10 event. Never blocks checkout."""
        items = g.cart.items
        # Senso only scores claims about the organization's own content, so each claim is phrased as
        # "our catalog" and sent as author=organization; plain "X costs $Y" comes back unscored.
        lines = []
        for i in items:
            n = i.product.name
            lines.append(f"Our catalog lists {n} from {i.product.source} at ${i.product.price:.2f}.")
            if i.product.ingredients:
                lines.append(f"In our catalog, the ingredients of {n} are {', '.join(i.product.ingredients)}.")
            if i.status == "pass":  # only products whose ingredients were actually checked may claim this
                lines += [f"In our catalog, {n} does not list {a} as an ingredient."
                          for a in sorted({a for p in profiles for a in p.allergens})]
        text = " ".join(lines)
        inputs, ctx = {"senso": "fact_check", "statement": text, "question": g.request}, []
        try:
            res = self.senso.check(text, f"{g.request} (checking this cart against our catalog)")
        except Exception as e:
            self._log(audit, g, "F10", inputs, ctx, f"Senso fact-check failed: {e}. Checkout not blocked.")
            return
        inputs["claims"] = [{"claim": c.get("claim_text"), "verdict": c.get("verdict")} for c in res.get("claims", [])]
        ctx = [f"senso:eval_run_id={res.get('id')}"]
        # shortcut: a claim is tied to an item by the product name appearing in its text; upgrade if the judge paraphrases names
        hit = lambda verdict: [i for i in items if any(
            i.product.name.lower() in f"{c.get('claim_text')} {c.get('source_text')}".lower()
            for c in res.get("claims", []) if c.get("verdict") == verdict)]
        conflicts = hit("conflict")
        # Only an unsupported INGREDIENT claim makes an item unconfirmed. An unsupported price claim is
        # logged below but must not flip an item whose ingredient list passed the deterministic check.
        def ingredient_claim(c) -> bool:
            return "ingredient" in f"{c.get('claim_text')} {c.get('source_text')}".lower()
        unsupported = [i for i in items if i not in conflicts and any(
            c.get("verdict") == "unsupported" and ingredient_claim(c)
            and i.product.name.lower() in f"{c.get('claim_text')} {c.get('source_text')}".lower()
            for c in res.get("claims", []))]
        for i in unsupported:
            ranking = i.reason.split(". ", 1)[1] if i.status == "pass" and ". " in i.reason else ""
            i.status = "unknown"
            i.alerts = i.alerts + ["Senso could not support an ingredient claim about this product"]
            i.reason = (self._unknown_reason(i.alerts) + " " + ranking).strip()  # keep price and ranking facts
        g.cart.items = [i for i in items if i not in conflicts]
        tally = ", ".join(f"{n} {v}" for v in ("verified", "conflict", "unsupported", "not_verifiable")
                          if (n := sum(c.get("verdict") == v for c in res.get("claims", []))))
        self._log(audit, g, "F10", inputs, ctx,
                  f"Senso fact-check {res.get('status')} (run {res.get('id')}): {tally or 'no claim verdicts'}. "
                  + (f"Removed before checkout, claim conflicts with Senso context: {', '.join(i.product.name for i in conflicts)}. " if conflicts else "")
                  + (f"Marked unknown, claim unsupported: {', '.join(i.product.name for i in unsupported)}." if unsupported else ""))

    def _checkout(self, g: Gathering, audit: list[AuditEvent], what: str) -> None:
        g.checkout_url = self.tools.create_checkout(g.cart)
        self._log(audit, g, "F7", {"items": [(i.product.id, i.quantity) for i in g.cart.items]},
                  [f"product:{i.product.id}@{i.product.source}" for i in g.cart.items],
                  f"{what}: {len(g.cart.items)} items, total ${quote(g.cart)['total']:.2f} with estimated shipping and tax, "
                  f"checkout {g.checkout_url}.")

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
                profiles = profiles or [self._profile(i) for i in g.guest_ids]
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

    def mark_paid(self, gathering_id: str, notify: bool = True, intent: dict | None = None) -> Gathering:
        """intent {"id", "amount"}: paid by the saved card (autopay), not by the Checkout Session."""
        with self._lock:  # the watcher and a "paid" text can race; only one gets past the status check
            g, audit = self._open(gathering_id, "awaiting_payment")
            g.status = "fulfilling"
            self._save(g, audit)

        if addr := getattr(self.tools, "shipping_address", lambda c: None)(g.cart):  # the address Stripe collected
            g.ship_to = g.cart.ship_to = addr
            self._save(g, audit)
        # F13 virtual card: shortcut: mocked, Stripe Issuing is not enabled on this account
        last4 = f"{int(g.id, 16) % 10000:04d}"
        total = quote(g.cart)["total"]
        self._log(audit, g, "F13.card", {"card_last4": last4, "spending_limit": total, "single_use": True},
                  [f"cart_total:{total}"],
                  f"Created a single-use virtual card ending {last4} limited to ${total:.2f} "
                  "(simulated; Stripe Issuing is not enabled on this account).", simulated=True)

        # F13 fanout: one simulated retailer order per source, paid with that card
        sources = sorted({i.product.source for i in g.cart.items})
        orders = _run_all([lambda s=s: self.tools.place_order(g.cart, s) for s in sources])
        for s, oid in zip(sources, orders):
            self._log(audit, g, "F13", {"source": s, "order_id": oid, "card_last4": last4, "ship_to": g.ship_to},
                      [f"product:{i.product.id}" for i in g.cart.items if i.product.source == s],
                      f"Placed order {oid} with {s}, paid with virtual card ending {last4}, "
                      f"shipping to {g.ship_to} (simulated).", simulated=True)

        if intent:  # F9: charge_saved charged exactly the quoted total
            ok = intent["amount"] == round(total * 100)
            self._log(audit, g, "F9", {"payment_intent": intent["id"], "amount_cents": intent["amount"]},
                      [f"cart_total:{total}"], "Saved-card charge matches the cart." if ok
                      else "Saved-card charge does NOT match the cart.")
        else:
            ok = self.tools.verify_checkout(g.cart)  # F9
            self._log(audit, g, "F9", {"checkout_url": g.checkout_url}, [f"cart_total:{g.cart.total}"],
                      "Checkout session matches the cart." if ok else "Checkout session does NOT match the cart.")
            who = self.sender(g.id)
            if who and not self.card(who) and (c := self.tools.saved_card(g.cart)):  # first chat payment saves it
                self.set_card(who, **{k: c[k] for k in ("customer", "payment_method", "last4", "brand")},
                              autopay=False, limit=float(os.environ.get("AUTOPAY_LIMIT", "50")))
        self._log(audit, g, "F11", {}, [f"profile:{i}" for i in g.guest_ids],
                  "Feedback will be recorded into each profile after the dinner.")
        g.status = "done"
        self._save(g, audit)
        if notify and (who := self.sender(g.id)):  # group dinners from POST /gatherings have no sender
            text = self.receipt(g.id)
            self._update("outbox.json", [], lambda d: d.append({"sender": who, "text": text}))
        due = datetime.now(timezone.utc).timestamp() + float(os.environ.get("FEEDBACK_DELAY_SECONDS", "0") or 0)
        self._update("followups.json", {}, lambda d: d.setdefault(g.id, {"due": due, "sent": False}))
        self.send_followups()  # after the receipt; with a delay the watcher tick sends it later
        return g

    # ---- F11 follow-up: one short question per reachable person, once per gathering ----

    def _recipients(self, g: Gathering) -> list[dict]:
        out, who = [], self.sender(g.id)
        if who:
            out.append({"to": who, "person": who, "name": None, "role": "host"})
        if g.mode == "dinner":
            for i in g.guest_ids:
                p = self._profile(i)
                if p.contact and p.contact not in {r["to"] for r in out}:
                    out.append({"to": p.contact, "person": p.id, "name": p.name, "role": "guest", "host": who})
        return out

    def send_followups(self) -> int:
        """Queue every due, unsent follow-up; marked sent in the same locked step, so restarts never duplicate."""
        now, sent = datetime.now(timezone.utc).timestamp(), 0
        with self._lock:
            pending = self._update("followups.json", {}, lambda d: [k for k, v in d.items()
                                                                    if not v["sent"] and v["due"] <= now])
            for gid in pending:
                g, audit = self._load(gid)
                names = [i.product.name.split(",")[0] for i in (g.cart.items if g.cart else [])][:2]
                text = (f"How was the {' and '.join(names) or 'order'}? Anything you'd skip or change next time? "
                        "(One line is plenty.)")
                people = self._recipients(g)
                for r in people:
                    self._update("outbox.json", [], lambda d, r=r: d.append({"sender": r["to"], "text": text}))
                    self._update("awaiting.json", {}, lambda d, r=r: d.__setitem__(r["to"], {**r, "gathering_id": gid}))
                self._log(audit, g, "F11", {"recipients": [r["person"] for r in people], "text": text},
                          [f"profile:{r['person']}" for r in people], f"Sent the follow-up to {len(people)} people.")
                self._save(g, audit)
                self._update("followups.json", {}, lambda d, gid=gid: d[gid].__setitem__("sent", True))
                sent += 1
        return sent

    def awaiting(self, phone: str) -> dict | None:
        """The follow-up this phone has not answered yet: {gathering_id, person, name, role, host?}."""
        p = self.dir / "notify" / "awaiting.json"  # read only: an unknown sender must not create files
        with self._lock:
            return json.loads(p.read_text()).get(phone) if p.exists() else None

    def clear_awaiting(self, phone: str) -> None:
        self._update("awaiting.json", {}, lambda d: d.pop(phone, None))

    def log_event(self, gathering_id: str, node: str, inputs: dict, context: list[str], decision: str) -> None:
        with self._lock:
            g, audit = self._load(gathering_id)
            self._log(audit, g, node, inputs, context, decision)
            self._save(g, audit)

    def stop(self, gathering_id: str) -> Gathering:
        g, audit = self._load(gathering_id)
        prev = g.status
        g.status = "stopped"
        self._log(audit, g, "F8", {"previous_status": prev}, [], "Kill switch: stopped and handed control to the host.")
        self._save(g, audit)
        return g
