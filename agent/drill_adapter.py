"""Firedrill http.v1 adapter: message in, plain-text cart summary out. Drill only; agent/api.py is untouched.

Run: PORT=8010 python -m agent.drill_adapter     (or: uvicorn agent.drill_adapter:app --port 8010)
Never calls mark_paid: payment needs the human.
"""
import os
import tempfile

from fastapi import FastAPI
from pydantic import BaseModel

GUEST = "g3"  # Chen, peanut allergen
SHIP_TO = "100 Drill St, San Francisco, CA 94105"  # synthetic address

app = FastAPI(title="Firedrill adapter")
_wf = None
_replies: dict[str, str] = {}  # session key -> summary; shortcut: one cart per drill session, later turns repeat it


class Chat(BaseModel):
    message: str
    session: str = "default"


def _workflow():
    global _wf
    if _wf is None:  # same wiring as agent.api's lazy app, with a throwaway data dir
        from agent.llm import get_llm
        from agent.workflow import Workflow
        from contracts.fixtures import FakeTools

        if os.environ.get("STRIPE_SECRET_KEY") and os.environ.get("BRIGHTDATA_API_KEY"):
            from agent.products import BrightDataTools
            tools = BrightDataTools()
        elif os.environ.get("STRIPE_SECRET_KEY"):
            from agent.payments import StripeTools
            tools = StripeTools()
        else:
            tools = FakeTools()
        senso = None
        if os.environ.get("SENSO_API_KEY"):
            from agent.senso import Senso
            senso = Senso()
        _wf = Workflow(tools, get_llm(), data_dir=tempfile.mkdtemp(prefix="drill-"), senso=senso)
    return _wf


def _summary(g) -> str:
    lines = [f"Cart for your request ({len(g.cart.items)} item(s)):"]
    for i in g.cart.items:
        p = i.product
        lines.append(f"- {p.name} ({p.pack_size}) from {p.source}, ${p.price:.2f} x{i.quantity}. "
                     f"Status: {i.status}. Ingredients: {', '.join(p.ingredients) or 'not listed'}. "
                     f"Reason: {i.reason}" + (f" Alerts: {'; '.join(i.alerts)}." if i.alerts else ""))
    lines.append(f"Total: ${g.cart.total:.2f}.")
    lines.append("Checkout is a Stripe test-mode link and nothing has been paid. "
                 f"It is waiting for your approval: {g.checkout_url}")
    return "\n".join(lines)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/chat")
def chat(b: Chat):
    if b.session not in _replies:
        wf = _workflow()
        g = wf.start("drill-shopper", b.message, SHIP_TO, [GUEST])
        g = wf.approve_plan(g.id)  # shopping plan approved by the simulated user's message; payment is not
        _replies[b.session] = _summary(g) if g.cart and g.cart.items else (
            "I could not find any product that passed your allergy checks, so the cart is empty. Nothing was bought.")
    return {"reply": _replies[b.session]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8010")))
