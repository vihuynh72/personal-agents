"""Text conversation over iMessage: onboarding, then "get me X" runs the whole buy-for-myself flow to a pay link.

Control flow is deterministic; the model (system1) only extracts profile facts and classifies a message.
The only human gate is payment: chat fulfils only after Stripe itself reports the session paid.
"""
import logging
import os

from contracts.models import GuestProfile

from .profiles import ProfileStore
from .workflow import Workflow, _ask

log = logging.getLogger(__name__)

ONBOARD = ("Hi! I'm your shopping agent. In one message: what can't you have (allergies, diet), "
           "and how do you like to shop (organic, favourite brands, cheapest, a budget)?")

_EXTRACT = ("TASK: profile. Extract shopping facts from this message. Reply with JSON only: "
            '{"name": "<first name or null>", "allergens": ["<lowercase singular food, e.g. peanut>"], '
            '"restrictions": ["<diet, e.g. vegetarian, halal>"], '
            '"preferences": ["<short soft style keyword: organic, a brand name, cheapest, or a budget as under $N>"]}. '
            "Allergens and diets are safety facts; preferences are only style. Use [] when none.\nMessage: ")

_INTENT = ("TASK: intent. Classify this text to a shopping agent. Reply with JSON only: "
           '{"intent": "order" (they want something bought) or "update" (they are changing allergies, diet or '
           'preferences) or "paid" (they say they paid) or "other"}.\nMessage: ')


def _strs(d: dict, k: str) -> list[str]:
    v = d.get(k)
    return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []


def _merge(a: list[str], b: list[str]) -> list[str]:
    seen = {x.lower() for x in a}
    return a + [x for x in b if x.lower() not in seen]


class Chat:
    def __init__(self, workflow: Workflow, profiles: ProfileStore, llm):
        self.wf, self.store, self.llm = workflow, profiles, llm

    def handle(self, sender: str, text: str) -> str:
        step = "read your profile"
        try:
            profile = self.store.get(sender)
            if profile is None and not self.store.pending(sender):
                self.store.set_pending(sender, True)
                return ONBOARD
            if profile is None:
                step = "save your profile"
                return self._onboard(sender, text)
            step = "understand your message"
            intent, _ = _ask(self.llm.system1, _INTENT + text, {})
            intent = intent.get("intent")
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
            if intent != "order":
                return "Tell me what to get (e.g. \"get me coffee\"), or tell me a new preference or allergy."
            step = "plan your order"
            g = self.wf.start(host=profile.name or sender, request=text, ship_to=os.environ.get("DEFAULT_SHIP_TO", "address on file"),  # shortcut: no address field on GuestProfile yet
                              guest_ids=[sender])
            self.wf.set_sender(g.id, sender)
            step = "build your cart"
            g = self.wf.approve_plan(g.id)  # buy-for-myself: the plan gate is skipped by design; payment is the gate
            return self._cart(g)
        except Exception:
            log.exception("chat step failed: %s", step)
            return f"Sorry, I couldn't {step}. Nothing was bought. Please try again in a moment."

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
        if not ok:
            out["preferences"] = [text.strip()]  # model unusable after one retry: keep their words as one preference
        return out

    def _onboard(self, sender: str, text: str) -> str:
        facts = self._extract(text)
        if not (facts["name"] or facts["allergens"] or facts["restrictions"] or facts["preferences"]):
            return "I didn't catch anything there. " + ONBOARD.split("! ", 1)[1]
        profile = self.store.save(GuestProfile(id=sender, name=facts["name"] or sender, allergens=facts["allergens"],
                                               restrictions=facts["restrictions"], preferences=facts["preferences"]))
        self.store.set_pending(sender, False)
        return f"Saved. {self._summary(profile)} What should I get you?"

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
