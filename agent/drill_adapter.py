"""Firedrill http.v1 adapter: each message goes through the real conversation (agent.chat.Chat). Drill only;
agent/api.py is untouched.

Run: PORT=8010 python -m agent.drill_adapter     (or: uvicorn agent.drill_adapter:app --port 8010)
Never calls mark_paid: payment needs the human.
"""
import hashlib
import os
import tempfile
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

SHIP_TO = "100 Drill St, San Francisco, CA 94105"  # synthetic address
_BOOT = uuid.uuid4().hex  # a fresh shopper per process start, so a rerun never meets an old profile

app = FastAPI(title="Firedrill adapter")
_chat = None


class Chat(BaseModel):
    message: str
    session: str = "default"


def _agent():
    global _chat
    if _chat is None:  # same wiring as agent.api's lazy app, with a throwaway data dir
        from agent.chat import Chat as AgentChat
        from agent.llm import get_llm
        from agent.profiles import ProfileStore
        from agent.workflow import Workflow
        from contracts.fixtures import FakeTools

        d = tempfile.mkdtemp(prefix="drill-")
        if os.environ.get("STRIPE_SECRET_KEY") and os.environ.get("BRIGHTDATA_API_KEY"):
            from agent.products import BrightDataTools
            tools = BrightDataTools(d)
        elif os.environ.get("STRIPE_SECRET_KEY"):
            from agent.payments import StripeTools
            tools = StripeTools(d)
        else:
            tools = FakeTools()
        senso = None
        if os.environ.get("SENSO_API_KEY"):
            from agent.senso import Senso
            senso = Senso()
        os.environ.setdefault("DEFAULT_SHIP_TO", SHIP_TO)
        store, llm = ProfileStore(d), get_llm()
        _chat = AgentChat(Workflow(tools, llm, data_dir=d, senso=senso, profiles=store), store, llm)
    return _chat


def _sender(session: str) -> str:
    """One shopper per drill session (and per process start); the id fits ProfileStore's safe-id rule."""
    return "drill-" + hashlib.sha256(f"{_BOOT}:{session}".encode()).hexdigest()[:16]


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/chat")
def chat(b: Chat):
    try:
        return {"reply": _agent().handle(_sender(b.session), b.message)}
    except Exception as e:  # report it as the agent's honest reply, not a 500
        return {"reply": (f"Something went wrong on my side ({type(e).__name__}: {str(e)[:200]}). "
                          "Nothing was added to a checkout and nothing was bought or paid.")}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8010")))
