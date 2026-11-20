"""Text conversation over iMessage: at most one onboarding question, then "get me X" runs the whole
buy-for-myself flow to a pay link. Questions about the cart are answered from the cart's own facts.

Control flow is deterministic; the model (system1) only extracts profile facts and classifies a message.
The only human gate is payment: chat fulfils only after Stripe itself reports the session paid.
"""
import logging
import os
import re

from contracts.models import GuestProfile

from .profiles import ProfileStore
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
            '"preferences": ["<short soft style keyword: organic, a brand name, cheapest, or a budget as under $N>"], '
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

_NONE = re.compile(r"(none|no|nope|nothing|n/?a|no thanks)[.! ]*", re.I)


def _strs(d: dict, k: str) -> list[str]:
    v = d.get(k)
    return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []


def _merge(a: list[str], b: list[str]) -> list[str]:
    seen = {x.lower() for x in a}
    return a + [x for x in b if x.lower() not in seen]


class Chat:
    def __init__(self, workflow: Workflow, profiles: ProfileStore, llm):
        self.wf, self.store, self.llm = workflow, profiles, llm

    def _intent(self, text: str) -> str | None:
        return _ask(self.llm.system1, _INTENT + text, {})[0].get("intent")

    def handle(self, sender: str, text: str) -> str:
        step = "read your profile"
        try:
            profile = self.store.get(sender)
            if profile is None and not self.store.pending(sender):
                step = "understand your message"
                request = text.strip() if self._intent(text) == "order" else ""
                self.store.set_pending(sender, True)
                # shortcut: the remembered request lives in the pending marker file; ProfileStore has no field for it
                self.store._path(sender, ".pending").write_text(request)
                return ASK_ONE if request else ONBOARD
            if profile is None:
                step = "save your profile and build your cart"
                return self._onboard(sender, text)
            step = "understand your message"
            intent = self._intent(text)
            if intent == "update":
                step = "update your profile"
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

    def _order(self, sender: str, profile: GuestProfile, request: str) -> str:
        g = self.wf.start(host=profile.name or sender, request=request,
                          ship_to=os.environ.get("DEFAULT_SHIP_TO", "address on file"),  # shortcut: no address field on GuestProfile yet
                          guest_ids=[sender], mode="self")
        self.wf.set_sender(g.id, sender)
        g = self.wf.approve_plan(g.id)  # buy-for-myself: the plan gate is skipped by design; payment is the gate
        return self._cart(g)

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
        facts = {"name": None, "allergens": [], "restrictions": [], "preferences": [], "request": None} \
            if _NONE.fullmatch(text.strip()) else self._extract(text)
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
        lines = [f"- {i.product.name} ({i.product.pack_size or 'size n/a'}), ${i.product.price:.2f} x{i.quantity}: {i.reason}"
                 + (" NEEDS YOUR CONFIRMATION." if i.status == "unknown" else "") for i in items]
        web = os.environ.get("WEB_URL")
        link = f"{web.rstrip('/')}/gatherings/{g.id}" if web else g.checkout_url
        return "\n".join(["Here's your cart:", *lines, f"Total ${g.cart.total:.2f}. Review and pay: {link}"])
