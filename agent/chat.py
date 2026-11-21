"""Text conversation over iMessage: at most one onboarding question, then "get me X" runs the whole
buy-for-myself flow to a pay link. Questions about the cart are answered from the cart's own facts.

Control flow is deterministic; the model (system1) only extracts profile facts and classifies a message.
The only human gate is payment: chat fulfils only after Stripe itself reports the session paid.
"""
import json
import logging
import os
import re

from contracts.models import GuestProfile

from .cart_page import cart_url
from .connect import hint
from .pricing import quote
from .profiles import ProfileStore
from .llm import FakeLLM
from .workflow import Workflow, _ask

log = logging.getLogger(__name__)

# the one question each new sender gets: greeting-only first text asks both things at once
ONBOARD = ("Hi! I'm your shopping agent. One question: what should I get you, and is there anything you can't have "
           "or prefer (organic, a brand, a budget)? Reply 'none' if nothing to avoid.")
ASK_ONE = ("Got it. One question before I shop: anything you can't have, and any preference "
           "(organic, a brand, a budget)? Reply 'none' if not.")

_EXTRACT = ("TASK: profile. Extract shopping facts from this message. Reply with JSON only: "
            '{"name": "<first name or null>", "allergens": ["<lowercase singular food, e.g. peanut>"], '
            '"restrictions": ["<diet, e.g. vegetarian, halal>"], '
            '"preferences": ["<short soft style keyword: organic, a brand name, cheapest, a budget as under $N, or a cuisine or food culture such as vietnamese>"], '
            '"request": "<what they want bought now, in their words, or null>"}. '
            "Allergens and diets are safety facts; preferences are only style. Use [] when none.\nMessage: ")

_INTENT = ("TASK: intent. Classify this text to a shopping agent. Reply with JSON only: "
           '{"intent": "order" (they want something bought, including a vague meal request like "what\'s for dinner") '
           'or "question" (they ask about the cart they were sent: safety, ingredients, price) '
           'or "change" (they correct the cart they were sent: a different form, cheaper, organic instead) '
           'or "update" (they are changing allergies, diet or preferences) '
           'or "paid" (they say they paid) or "other"}.\nMessage: ')

_ANSWER = ("TASK: answer. Rephrase these facts as a reply to the shopper's question in 1 to 3 short sentences. "
           "Use only these facts and nothing else. Never say or imply the product is safe.\n")

_AUTOPAY = re.compile(r"\s*(?:(stop) autopay|autopay(?: (on|off)| limit \$?(\d+(?:\.\d+)?))?)[.!\s]*", re.I)

# a route switch for a current food cart: forced, never re-classified
_TO_COOK = re.compile(r"\s*(?:cook instead|i want to cook|i'?d rather cook)[.!\s]*", re.I)
_TO_ORDER = re.compile(r"\s*(?:order in instead|just order it)[.!\s]*", re.I)
_HEAD = {"order": "Ordering in (prepared food):", "cook": "Cooking (groceries):"}
SWITCH = "Say 'cook instead' or 'order in instead' to switch."

_NONE = re.compile(r"(none|no|nope|nothing|n/?a|no thanks)[.! ]*", re.I)


def _strs(d: dict, k: str) -> list[str]:
    v = d.get(k)
    return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []


def _merge(a: list[str], b: list[str]) -> list[str]:
    seen = {x.lower() for x in a}
    return a + [x for x in b if x.lower() not in seen]


# a reply to the follow-up that says nothing worth remembering
_CHEAP = re.compile(r"[\W_]*((fine|good|great|ok|okay|no|nope|nothing|none|all|it|was|all good|thanks|thank you|thx|"
                    r"ty|yes|yep|perfect|loved it|nah)[\W_]*)*", re.I)


def _learned(res: dict) -> str:
    """One line from memory.add's result; at most one yes/no question, only for a conflict that needs it."""
    said = []
    for f in res.get("added") or []:
        kind, plus, v = f.get("kind"), str(f.get("polarity", "+")).startswith("+"), f.get("value")
        if kind == "name":
            continue
        liked = plus if kind == "preference" else (not plus if kind == "dislike" else None)
        said.append(f"you liked {v}" if liked is True else f"you didn't like {v}" if liked is False else
                    f"you avoid {v}" if plus else f"you no longer avoid {v}")
    out = f"Thanks. Noted: {'; '.join(said)}." if said else "Thanks, noted."
    ask = next((c for c in res.get("conflicts") or [] if c.get("needs_confirmation")), None)
    return out + (f" One check: are you still avoiding {ask.get('value')}? (yes/no)" if ask else "")


class Chat:
    def __init__(self, workflow: Workflow, profiles: ProfileStore, llm, memory=None):
        self.wf, self.store, self.llm, self.memory = workflow, profiles, llm, memory  # memory: agent.memory.Memory or None
        self._asked: dict[str, str] = {}  # sender -> value awaiting a yes/no

    def _feedback(self, sender: str, fb: dict, text: str) -> str:
        """The reply to a post-order follow-up: into memory (or the audit trail), then the mark is cleared."""
        gid, person = fb["gathering_id"], fb["person"]
        self.wf.clear_awaiting(sender)
        if _CHEAP.fullmatch(text.strip()):
            self.wf.log_event(gid, "F11", {"from": person, "feedback": text}, [f"profile:{person}"],
                              "Feedback had nothing to change; recorded nothing.")
            return "Thanks!"
        reply, changed = "Thanks, noted.", "Stored the raw feedback (no memory attached)."
        if self.memory:
            res = self.memory.add(person, text, "feedback")
            reply = _learned(res)
            changed = f"Memory added {res.get('added') or []}; conflicts {res.get('conflicts') or []}."
        g, host = self.wf.get(gid), fb.get("host")
        item = next((m for m in g.menu if any(re.search(rf"\b{re.escape(w)}\b", text, re.I)
                                             for w in m.split() if len(w) > 3)), None)
        if fb.get("role") == "guest" and host and item:
            note = f"Guest {fb.get('name') or person} said about {item}: {text}"
            if self.memory:
                before = self.store.get(host)
                self.memory.add(host, note, "guest")
                after = self.store.get(host)
                if before and after and (after.allergens, after.restrictions) != (before.allergens, before.restrictions):
                    # a guest's safety facts are never the host's
                    self.store.save(after.model_copy(update={"allergens": before.allergens,
                                                             "restrictions": before.restrictions}))
            changed += f" Recorded for host {host}: {note}"
        self.wf.log_event(gid, "F11", {"from": person, "feedback": text}, [f"profile:{person}"], changed)
        return reply

    def _intent(self, text: str) -> str | None:
        # Classification must never be the reason a shopper gets an apology: on any model failure or an
        # unexpected label, fall back to the deterministic keyword classifier.
        try:
            intent = _ask(self.llm.system1, _INTENT + text, {})[0].get("intent")
        except Exception:
            log.exception("intent model failed")
            intent = None
        if intent not in ("order", "update", "paid", "question", "change", "other"):
            intent = json.loads(FakeLLM().system1(_INTENT + text)).get("intent")
        return intent

    def _confirm(self, sender: str, text: str) -> str | None:
        """Answer to the single safety question. Only the person's own 'no' removes a restriction."""
        value = self._asked.pop(sender, None)
        word = re.sub(r"[^a-z]", "", text.lower())[:4]
        if value is None or not self.memory or not word.startswith(("yes", "yep", "yeah", "no", "nope", "nah")):
            return None
        if word.startswith("y"):
            return f"Got it. Still avoiding {value}."
        self.memory.add(sender, f"I can eat {value} now. I am no longer allergic to {value}.", "chat")
        return f"Updated. I'll stop avoiding {value} for you."

    def handle(self, sender: str, text: str) -> str:
        if (reply := self._confirm(sender, text)) is not None:
            return reply
        if m := _AUTOPAY.fullmatch(text):
            return self._autopay(sender, m)
        reply = self._handle(sender, text)
        if (m := re.search(r"are you still avoiding (.+?)\? \(yes/no\)", reply)):
            self._asked[sender] = m.group(1)
        return reply

    def _handle(self, sender: str, text: str) -> str:
        step = "read your profile"
        try:
            if fb := self.wf.awaiting(sender):
                step = "understand your message"
                intent = self._intent(text)
                if not (intent in ("order", "paid") or (intent in ("question", "change") and self._current(sender))):
                    step = "save your feedback"
                    return self._feedback(sender, fb, text)
            step = "read your profile"
            profile = self.store.get(sender)
            if profile is None and not self.store.pending(sender):
                step = "understand your message"
                request = text.strip() if self._intent(text) == "order" else ""
                self.store.set_pending(sender, True)
                # shortcut: the remembered request lives in the pending marker file; ProfileStore has no field for it
                self.store._path(sender, ".pending").write_text(request)
                return (ASK_ONE if request else ONBOARD) + hint(sender)
            if profile is None:
                step = "save your profile and build your cart"
                return self._onboard(sender, text)
            current = self._current(sender)
            to = "cook" if _TO_COOK.fullmatch(text) else "order" if _TO_ORDER.fullmatch(text) else None
            if to and current and current.fulfil in ("cook", "order"):
                step = "switch your order"
                self.wf.stop(current.id)  # reuses the "change" path: stop the old cart, re-run the request
                return self._order(sender, profile, current.request, fulfil=to)
            step = "understand your message"
            intent = self._intent(text)
            if intent == "update":
                step = "update your profile"
                if self.memory:  # every profile change goes through memory's conflict loop
                    return f"Updated. {self._summary(self.memory.add(sender, text, 'chat')['profile'])}"
                facts = self._extract(text)
                profile = profile.model_copy(update={k: _merge(getattr(profile, k), facts[k])
                                                     for k in ("allergens", "restrictions", "preferences")})
                self.store.save(profile)
                return f"Updated. {self._summary(profile)}"
            if intent == "paid":
                step = "check your payment"
                return self._paid(sender)
            current = self._current(sender)
            if intent == "question":
                step = "answer your question"
                return self._answer(current, profile, text) if current else \
                    "I don't have a cart waiting for you. Tell me what to get (e.g. \"get me coffee\")."
            if intent == "change" and current:
                step = "change your cart"
                self.wf.stop(current.id)  # the watcher stops waiting on the old cart
                return self._order(sender, profile, f"{current.request}. Correction: {text}")
            if intent not in ("order", "change"):
                return "Tell me what to get (e.g. \"get me coffee\"), or tell me a new preference or allergy."
            step = "build your cart"
            return self._order(sender, profile, text)
        except Exception:
            log.exception("chat step failed: %s", step)
            return f"Sorry, I couldn't {step}. Nothing was bought. Please try again in a moment."

    def _order(self, sender: str, profile: GuestProfile, request: str, fulfil: str | None = None) -> str:
        g = self.wf.start(host=profile.name or sender, request=request,
                          ship_to=os.environ.get("DEFAULT_SHIP_TO", "address on file"),  # shortcut: no address field on GuestProfile yet
                          guest_ids=[sender], mode="self", fulfil=fulfil)
        if g.fulfil not in _HEAD:
            return self._built(sender, g)
        try:
            body = self._built(sender, g)
        except ValueError:  # nothing passed every check: say so on this route instead of a generic apology
            body = f"I couldn't find anything for \"{g.request}\" that is safe for you, so there's nothing to pay."
        return f"{_HEAD[g.fulfil]}\n{body}\n{SWITCH}"

    def _built(self, sender: str, g) -> str:
        self.wf.set_sender(g.id, sender)
        g = self.wf.approve_plan(g.id)  # buy-for-myself: the plan gate is skipped by design; payment is the gate
        # autopay: the shopper opted in once, so a saved-card charge under their limit replaces the pay link
        if (a := self.wf.autopay(g.id, sender)) and a["charged"]:
            return f"Charged ${quote(g.cart)['total']:.2f} to your card ending {a['card']['last4']}.\n" + self.wf.receipt(g.id)
        return self._cart(g) + (f"\nNot charged automatically: {a['reason']}" if a else "")

    def _autopay(self, sender: str, m) -> str:
        """AUTOPAY / AUTOPAY OFF / STOP AUTOPAY / AUTOPAY LIMIT 80. Explicit opt-in only; off applies to the next order."""
        c = self.wf.card(sender)
        if not c:
            return "Autopay needs a saved card. Pay once through the order link first, then reply AUTOPAY."
        if m.group(1) or (m.group(2) or "").lower() == "off":
            self.wf.set_card(sender, autopay=False)
            return "Autopay is off. I'll send you the order link to pay each time."
        if m.group(3):
            limit = min(float(m.group(3)), 200.0)  # hard cap on what autopay may charge without a click
            self.wf.set_card(sender, limit=limit)
            return f"Autopay limit is now ${limit:g}." + ("" if c.get("autopay") else " Reply AUTOPAY to turn it on.")
        self.wf.set_card(sender, autopay=True)
        return (f"Autopay is on for orders under ${c['limit']:g}, card ending {c['last4']}. "
                "Reply AUTOPAY OFF any time.")

    def _current(self, sender: str):
        waiting = [i for i in self.wf.gatherings_of(sender) if self.wf.get(i).status == "awaiting_payment"]
        return self.wf.get(waiting[-1]) if waiting else None

    def _answer(self, g, profile: GuestProfile, question: str) -> str:
        """Deterministic facts from the cart; the model may only rephrase them, and never into a safety assurance."""
        avoid = ", ".join(profile.allergens + profile.restrictions)
        parts = []
        for i in g.cart.items[:3]:
            p, ings = i.product, ", ".join(i.product.ingredients)
            s = f"{p.name} ({p.pack_size or 'size n/a'}, ${p.price:.2f} from {p.source})"
            if i.status == "pass":
                s += f": the store lists {ings}, and none of that matches what you avoid ({avoid or 'nothing given'})."
            else:
                s += f" needs confirmation: {'; '.join(i.alerts) or 'not every check passed'}."
            if i.status == "pass" and ". " in i.reason:
                s += " " + i.reason.split(". ", 1)[1]  # the ranking part: preference, unit price, options compared
            # always answer the price question, whatever the safety status
            cheaper = sorted((a for a in i.alternatives if a.price < p.price), key=lambda a: a.price)[:1]
            s += f" On price: ${p.price:.2f} for {p.pack_size or 'this pack'}, compared against {len(i.alternatives)} other option(s)."
            s += (f" The lowest price to pay is {cheaper[0].name[:50]} at ${cheaper[0].price:.2f} "
                  f"({cheaper[0].pack_size or 'size n/a'}); I picked this one for the lower cost per unit. "
                  f"Say 'the cheaper one' to switch." if cheaper else " Nothing I found costs less to buy.")
            parts.append(s)
        facts = " ".join(parts) + (" The store's ingredient list does not cover cross-contamination, \"may contain\" "
                                   "warnings or the factory, so I can't confirm those; please check the package.")
        try:
            out = (self.llm.system2(f"{_ANSWER}Facts: {facts}\nQuestion: {question}") or "").strip()
        except Exception:
            out = ""
        return facts if not out or re.search(r"\bsafe", out, re.I) else out

    def _paid(self, sender: str) -> str:
        """Stripe is the only proof of payment; the text just triggers an immediate check."""
        gids = self.wf.gatherings_of(sender)
        waiting = [i for i in gids if self.wf.get(i).status == "awaiting_payment"]
        if waiting:
            # notify=False: the receipt goes back as this reply, not also through the outbox
            return self.wf.receipt(waiting[-1]) if self.wf.check_paid(waiting[-1], notify=False) else \
                "I don't see the payment yet."
        done = [i for i in gids if self.wf.get(i).status == "done"]
        return self.wf.receipt(done[-1]) if done else "I don't see the payment yet."

    def _extract(self, text: str) -> dict:
        facts, ok = _ask(self.llm.system1, _EXTRACT + text, {})
        out = {k: _strs(facts, k) for k in ("allergens", "restrictions", "preferences")}
        out["name"] = facts.get("name") if isinstance(facts.get("name"), str) else None
        out["request"] = facts.get("request") if isinstance(facts.get("request"), str) and facts["request"].strip() else None
        if not ok:
            out["preferences"] = [text.strip()]  # model unusable after one retry: keep their words as one preference
        return out

    def _onboard(self, sender: str, text: str) -> str:
        """The answer to the one question: save the profile, then shop at once if a request is known. Never re-asks."""
        remembered = self.store._path(sender, ".pending").read_text().strip()
        none = _NONE.fullmatch(text.strip())
        if self.memory:
            profile = self.store.save(GuestProfile(id=sender, name=sender))  # memory rewrites an existing profile
            if not none:
                profile = self.memory.add(sender, text, "chat")["profile"]
            facts = {"request": None if none or remembered else self._extract(text)["request"]}
        else:
            facts = {"name": None, "allergens": [], "restrictions": [], "preferences": [], "request": None} \
                if none else self._extract(text)
            profile = self.store.save(GuestProfile(id=sender, name=facts["name"] or sender, allergens=facts["allergens"],
                                                   restrictions=facts["restrictions"], preferences=facts["preferences"]))
        self.store.set_pending(sender, False)
        request = remembered or facts["request"]
        if not request:
            return f"Saved. {self._summary(profile)} Text me what you need any time."
        return f"Saved. {self._summary(profile)}\n{self._order(sender, profile, request)}"

    @staticmethod
    def _summary(p: GuestProfile) -> str:
        cant = ", ".join(p.allergens + p.restrictions) or "nothing"
        return f"Avoiding: {cant}. Preferences: {', '.join(p.preferences) or 'none'}."

    @staticmethod
    def _cart(g) -> str:
        items = g.cart.items if g.cart else []
        if not items:
            return f"I couldn't find anything for \"{g.request}\" that is safe for you, so there's nothing to pay."
        cut = lambda t, n: t if len(t) <= n else t[:n - 3].rstrip() + "..."
        lines = [f"- {cut(i.product.name, 45)}, ${i.product.price:.2f} x{i.quantity}: {cut(i.reason, 80)}"
                 + (" NEEDS YOUR CONFIRMATION." if i.status == "unknown" else "") for i in items]
        q = quote(g.cart)
        return "\n".join(["Here's your cart:", *lines,
                          f"Subtotal ${q['subtotal']:.2f}, shipping ${q['shipping']:.2f}, est. tax ${q['tax']:.2f}. "
                          f"Total ${q['total']:.2f}.", f"Review and pay: {cart_url(g.id)}"])
