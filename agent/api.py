"""HTTP surface for the agent (node N3). web/ talks only to this."""
import logging

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from agent import cart_page
from agent.pricing import quote
from agent.profiles import _SAFE
from contracts.models import GuestProfile


class StartBody(BaseModel):
    host: str
    request: str
    ship_to: str
    guest_ids: list[str]


class MessageBody(BaseModel):
    sender: str
    text: str


class ImportBody(BaseModel):
    items: list[dict]  # {"text", "source", "when"?}


class CartBody(BaseModel):
    changes: list[dict]  # {"product_id", "quantity"} or {"product_id", "swap_to"}


def _out(g) -> dict:
    d = g.model_dump(mode="json")
    if g.cart is not None:
        d["cart"]["total"] = g.cart.total  # Cart.total is a property, so model_dump omits it
        d["quote"] = quote(g.cart)  # subtotal, shipping, tax, total: what the page shows and Stripe charges
    return d


def create_app(workflow, chat=None, profiles=None, memory=None) -> FastAPI:
    from agent.profiles import ProfileStore

    profiles = profiles or getattr(workflow, "profiles", None) or ProfileStore()
    app = FastAPI(title="Blackout")
    app.state.memory = memory  # Chat can be handed this; built on first use when not given

    def _memory():
        if app.state.memory is None:
            from agent.llm import get_llm
            from agent.memory import Memory
            app.state.memory = Memory(profiles, get_llm(), str(profiles.dir.parent))
        return app.state.memory
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

    @app.get("/cart/{gid}", response_class=HTMLResponse)  # the order page the agent texts
    def cart_view(gid: str):
        try:
            g, audit = workflow.get(gid), workflow.audit(gid)
        except KeyError:
            return HTMLResponse(cart_page.not_found(), status_code=404)
        return HTMLResponse(cart_page.render(g, audit))

    @app.post("/messages")  # iMessage bot contract: {"sender", "text"} -> {"reply"}
    def message(b: MessageBody):
        nonlocal chat
        if chat is None:
            from agent.chat import Chat
            from agent.llm import get_llm
            chat = Chat(workflow, profiles, get_llm())
        return {"reply": chat.handle(b.sender, b.text)}

    @app.get("/outbox")  # iMessage bot pulls: {"messages": [{"sender", "text"}]}; returned messages are removed
    def outbox():
        return {"messages": workflow.outbox_pop()}

    @app.get("/profiles/{pid}")
    def get_profile(pid: str):
        if (p := profiles.get(pid)) is None:
            raise KeyError(pid)
        return p.model_dump(mode="json")

    @app.put("/profiles/{pid}")
    def put_profile(pid: str, b: GuestProfile):
        return profiles.save(b.model_copy(update={"id": pid})).model_dump(mode="json")

    @app.post("/profiles/{pid}/import")  # Day 0: past messages, receipts, calendar entries
    def import_history(pid: str, b: ImportBody):
        r = _memory().add_many(pid, b.items)
        return {"profile": r["profile"].model_dump(mode="json"), "added": len(r["added"]), "conflicts": r["conflicts"]}

    @app.get("/profiles/{pid}/memory")
    def memory_history(pid: str):
        return _memory().history(pid)

    from agent import a2a
    conns = a2a.Connections(str(profiles.dir.parent))
    # Ryan's front end (web/), built with `vite build --base=/app/` and copied to agent/web_dist.
    _web = Path(__file__).parent / "web_dist"
    if _web.is_dir():
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import RedirectResponse as _Redirect
        app.mount("/app", StaticFiles(directory=str(_web), html=True), name="web")

        @app.get("/", include_in_schema=False)
        def _home():
            return _Redirect("/app/")
    @app.get("/try", include_in_schema=False)
    def _try():  # the app is the page people should see
        from fastapi.responses import RedirectResponse as _R
        return _R("/app/")

    @app.get("/chat", include_in_schema=False)
    def _chat():  # phone number in, then the real agent over POST /messages
        from fastapi.responses import HTMLResponse
        from agent.try_page import PAGE
        return HTMLResponse(PAGE)

    from agent import mockstore  # our own demo retailer, for the cloud ordering step
    app.include_router(mockstore.make_router(str(profiles.dir.parent)))

    def _llm():
        if getattr(workflow, "llm", None) is None:
            from agent.llm import get_llm
            workflow.llm = get_llm()
        return workflow.llm

    @app.post("/a2a/consent")  # owner lets `to`'s agent ask for owner's data within scopes
    def a2a_consent(b: dict):
        return {"scopes": sorted(conns.grant(b["owner"], b["to"], b["scopes"]))}

    @app.post("/a2a/plan")
    def a2a_plan(b: dict):
        return a2a.plan_gathering(b["host"], b["guests"], b["request"], b["candidate_times"], profiles, conns,
                                  getattr(workflow, "tools", None), _llm())

    @app.post("/a2a/message")  # the wire endpoint another deployment's agent calls
    def a2a_message(b: dict):
        m = b["message"]
        return a2a.PersonAgent(m["to"], profiles, conns, getattr(workflow, "tools", None), _llm()).handle(m)

    from agent import connect
    _OFF = {"detail": "Google connect is not configured (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET unset)."}

    @app.get("/connect/google")  # day 0, self-serve: the link in the first text
    def connect_google(sender: str):
        if (c := connect.config()) is None:
            return JSONResponse(_OFF, status_code=503)
        if not _SAFE.fullmatch(sender):
            return JSONResponse({"detail": "invalid sender"}, status_code=400)
        return RedirectResponse(connect.auth_url(c, connect.new_state(profiles.dir.parent, sender)), status_code=302)

    @app.get("/connect/google/callback")
    def connect_callback(code: str = "", state: str = ""):
        if (c := connect.config()) is None:
            return JSONResponse(_OFF, status_code=503)
        if not code or (sender := connect.take_state(profiles.dir.parent, state)) is None:
            return JSONResponse({"detail": "unknown or expired link; text me to get a new one"}, status_code=400)
        try:
            fetch = connect.make_fetcher(connect.exchange(c, code))  # the token lives only in this closure
        except Exception:
            logging.getLogger(__name__).exception("google token exchange failed")
            return HTMLResponse("Couldn't connect Google. Text me anything you can't have instead.", status_code=502)
        mem = _memory()
        connect.start(lambda: connect.run_import(sender, fetch, mem, workflow, profiles))
        return HTMLResponse(connect.PAGE)

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
            senso = None
            if os.environ.get("SENSO_API_KEY"):
                from agent.senso import Senso
                senso = Senso()
            from agent.chat import Chat
            from agent.profiles import ProfileStore
            llm, store = get_llm(), ProfileStore()
            wf = Workflow(tools, llm, senso=senso, profiles=store)
            from agent.memory import Memory
            memory = Memory(store, llm)
            _app = create_app(wf, Chat(wf, store, llm, memory=memory), store, memory)
            from agent.watcher import start
            start(wf)  # notices Stripe payments by polling; no webhook
        return _app
    raise AttributeError(name)
