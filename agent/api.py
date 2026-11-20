"""HTTP surface for the agent (node N3). web/ talks only to this."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class StartBody(BaseModel):
    host: str
    request: str
    ship_to: str
    guest_ids: list[str]


class CartBody(BaseModel):
    changes: list[dict]  # {"product_id", "quantity"} or {"product_id", "swap_to"}


def _out(g) -> dict:
    d = g.model_dump(mode="json")
    if g.cart is not None:
        d["cart"]["total"] = g.cart.total  # Cart.total is a property, so model_dump omits it
    return d


def create_app(workflow) -> FastAPI:
    app = FastAPI(title="Gathering agent")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(KeyError)
    def _404(_: Request, e: KeyError):
        return JSONResponse({"detail": f"not found: {e.args[0] if e.args else ''}"}, status_code=404)

    @app.exception_handler(ValueError)
    def _409(_: Request, e: ValueError):
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/gatherings")
    def start(b: StartBody):
        return _out(workflow.start(b.host, b.request, b.ship_to, b.guest_ids))

    @app.get("/gatherings/{gid}")
    def get(gid: str):
        return _out(workflow.get(gid))

    @app.post("/gatherings/{gid}/approve")
    def approve(gid: str):
        return _out(workflow.approve_plan(gid))

    @app.patch("/gatherings/{gid}/cart")
    def cart(gid: str, b: CartBody):
        return _out(workflow.update_cart(gid, b.changes))

    @app.post("/gatherings/{gid}/paid")  # the Stripe payment event will land here later
    def paid(gid: str):
        return _out(workflow.mark_paid(gid))

    @app.post("/gatherings/{gid}/stop")  # kill switch
    def stop(gid: str):
        return _out(workflow.stop(gid))

    @app.get("/gatherings/{gid}/audit")
    def audit(gid: str):
        return [e.model_dump(mode="json") for e in workflow.audit(gid)]

    return app


_app = None


def __getattr__(name):  # lazy `app` so importing this module (tests) needs neither workflow nor llm
    global _app
    if name == "app":
        if _app is None:
            from agent.llm import get_llm
            from agent.workflow import Workflow
            from contracts.fixtures import FakeTools

            import os
            if os.environ.get("STRIPE_SECRET_KEY") and os.environ.get("BRIGHTDATA_API_KEY"):
                from agent.products import BrightDataTools
                tools = BrightDataTools()
            elif os.environ.get("STRIPE_SECRET_KEY"):
                from agent.payments import StripeTools
                tools = StripeTools()
            else:
                tools = FakeTools()
            _app = create_app(Workflow(tools, get_llm()))
        return _app
    raise AttributeError(name)
