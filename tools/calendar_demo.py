"""Local demo page for the calendar flow: Accept (Google sign-in) -> Airbyte reads free/busy -> Cognee -> status.
  set -a && . ./.env && set +a
  uv run --no-project --python 3.12 --with airbyte --with fastapi --with uvicorn --with pydantic \
      python -m tools.calendar_demo           # then open http://localhost:8001
Real people (Ketki, Ryan) connect with Google; synthetic guests show labelled simulated data from Cognee.
Nobody presses sync: the page starts the agent's loop, which re-reads every connected calendar through Airbyte.
"""
import html
import logging
import os
import threading
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

from tools import google_calendar as gc
from tools.availability import AIRBYTE, SIMULATED, availability, decide, forget, records
from tools.cognee import Cognee
from tools.real import load_profiles
from tools.sync_calendars import INTERVAL, run_forever, sync_person

log = logging.getLogger(__name__)
PT = ZoneInfo("America/Los_Angeles")
START, END = datetime(2026, 11, 21, 19, 0, tzinfo=PT), datetime(2026, 11, 21, 21, 0, tzinfo=PT)
REAL = {"g1", "g4"}  # teammates with real Google accounts; everyone else is a synthetic demo guest

# Ryan's web/ (Vite dev server) reads availability and sends people here to connect.
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173").rstrip("/")
# The dinner times offered in web/src/data.ts SLOTS (two hours each, Pacific).
SLOTS = {
    "fri730": (datetime(2026, 11, 27, 19, 30, tzinfo=PT), datetime(2026, 11, 27, 21, 30, tzinfo=PT)),
    "sat7": (datetime(2026, 11, 28, 19, 0, tzinfo=PT), datetime(2026, 11, 28, 21, 0, tzinfo=PT)),
    "sun6": (datetime(2026, 11, 29, 18, 0, tzinfo=PT), datetime(2026, 11, 29, 20, 0, tzinfo=PT)),
}

@asynccontextmanager
async def _lifespan(_app):
    # The agent's own loop: nobody presses sync.
    names = lambda: {p.id: p.name for p in load_profiles().values()}  # noqa: E731  (sync_all falls back to the id)
    threading.Thread(target=run_forever, args=(names,), daemon=True, name="calendar-sync").start()
    yield


app = FastAPI(lifespan=_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[FRONTEND_ORIGIN], allow_methods=["GET"], allow_headers=["*"])
_notice = {"text": ""}
_return_to: dict[str, str] = {}  # person id -> web/ page to land on after Google



def _row(p, a) -> str:
    badge = {"free": "✅ FREE", "busy": "⛔ BUSY", "pending": "⏳ pending"}[a.status]
    if a.source == AIRBYTE and a.status == "pending":
        src = f"Google Calendar via Airbyte · last sync too old ({html.escape(a.synced_at or '')}), not trusted"
    elif a.source == AIRBYTE:
        src = f"Google Calendar via Airbyte · auto-synced {html.escape(a.synced_at or '')}"
    elif a.source == SIMULATED:
        src = "simulated demo data"
    else:
        src = "not connected" if p.id in REAL else "no calendar shared"
    actions = ""
    if p.id in REAL:
        actions = (f'<form method="post" action="/disconnect/{p.id}"><button>Disconnect</button></form>'
                   if gc.is_connected(p.id) else
                   f'<a class="btn" href="/connect/{p.id}">Connect Google Calendar</a>')
    return (f"<tr><td>{html.escape(p.name)}</td><td class='{a.status}'>{badge}</td>"
            f"<td class='src'>{src}</td><td class='act'>{actions}</td></tr>")


@app.get("/", response_class=HTMLResponse)
def home():
    profiles = load_profiles()
    try:
        answers = availability(list(profiles), START, END)
    except Exception as e:  # Cognee unreachable: say so instead of guessing
        log.warning("availability read failed: %r", e)
        return HTMLResponse(f"<p>Could not read Cognee: {html.escape(repr(e))}</p>", status_code=503)
    rows = "".join(_row(p, answers[p.id]) for p in profiles.values())
    note = f"<p class='note'>{html.escape(_notice['text'])}</p>" if _notice["text"] else ""
    _notice["text"] = ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Dinner availability</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="20"><style>
body{{font:16px system-ui;margin:2rem auto;max-width:860px;padding:0 1rem;color:#1c1c1c;background:#fff}}
table{{border-collapse:collapse;width:100%}}td{{padding:.6rem .5rem;border-bottom:1px solid #e5e5e5;vertical-align:middle}}
.free{{color:#11733a;font-weight:600}}.busy{{color:#b3261e;font-weight:600}}.pending{{color:#8a6d00;font-weight:600}}
.src{{color:#555;font-size:.9rem}}.act form{{display:inline}}button,.btn{{font:inherit;padding:.35rem .7rem;margin:.1rem;
border:1px solid #888;border-radius:6px;background:#fafafa;color:inherit;text-decoration:none;cursor:pointer}}
.note{{background:#eef5ff;padding:.6rem;border-radius:6px}}.flow{{color:#555;font-size:.9rem}}</style></head><body>
<h1>Saturday dinner · 7:00–9:00 PM (Pacific)</h1>
<p class="flow">Guest taps Allow (Google, free/busy only) → Airbyte Google Calendar connector reads free/busy →
stored in Cognee shared memory → agent reads it. Pending never counts as free.
The agent re-syncs every connected calendar every {INTERVAL // 60} min on its own.</p>{note}
<table>{rows}</table></body></html>"""


@app.get("/connect/{pid}")
def connect(pid: str, return_to: str = ""):
    if return_to:  # only back to our own front end, never to an arbitrary site
        if not (return_to == FRONTEND_ORIGIN or return_to.startswith(FRONTEND_ORIGIN + "/")):
            raise HTTPException(400, "return_to must be on the front end's origin")
        _return_to[gc.check_id(pid)] = return_to
    return RedirectResponse(gc.connect_url(pid))


def _name(pid: str) -> str:
    """Guests have a profile (g1..g6); a person signed in on web/ by email may not yet."""
    p = load_profiles().get(pid)
    return p.name if p else pid


def _back(pid: str, outcome: str) -> RedirectResponse:
    url = _return_to.pop(pid, None)
    if not url:
        return RedirectResponse("/", status_code=303)
    sep = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{sep}{urllib.parse.urlencode({'calendar': outcome, 'id': pid})}", status_code=303)


@app.get("/oauth/google/callback")
def callback(state: str = "", code: str = "", error: str = ""):
    pid = state.rpartition(".")[0]
    if error:  # the person pressed Cancel / Decline on Google's screen
        _notice["text"] = "Declined on Google's screen, so this guest stays pending."
        return _back(pid, "declined")
    try:
        pid = gc.finish_connect(code, state)
        n = sync_person(pid, _name(pid))
        _notice["text"] = f"Connected. Airbyte read {n} busy block(s) and saved them to Cognee."
        return _back(pid, "connected")
    except Exception as e:
        log.warning("connect failed: %r", e)
        _notice["text"] = f"Connect failed: {e}"
        return _back(pid, "failed")


@app.get("/api/availability")
def api_availability(ids: str, slots: str = ",".join(SLOTS)):
    """For web/: {"people": {id: {slot: {"status", "source", "synced_at"}}}} from Cognee.
    status is free | busy | pending; source is "airbyte/source-google-calendar", "simulated" or null."""
    people = [gc.check_id(i) for i in ids.split(",") if i]
    wanted = [x for x in slots.split(",") if x]
    if unknown := [x for x in wanted if x not in SLOTS]:
        raise HTTPException(400, f"unknown slot(s): {unknown}")
    recs = records()  # one Cognee read for every person and slot
    out = {pid: {x: vars(decide(recs.get(pid, (None, None))[1], *SLOTS[x])) for x in wanted} for pid in people}
    return {"people": out, "connected": [pid for pid in people if gc.is_connected(pid)]}


@app.post("/disconnect/{pid}")
def disconnect(pid: str):
    gc.disconnect(pid)
    forget(Cognee(), pid)
    _notice["text"] = "Disconnected: token deleted and availability removed from Cognee."
    return RedirectResponse("/", status_code=303)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
