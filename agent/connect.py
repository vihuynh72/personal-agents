"""Day 0, self-serve: a person connects Google from a link in their first text, and the server reads their
food receipts (Gmail metadata + snippet) and meals on their calendar into memory. Read-only scopes; the
access token lives only in memory for one import and is never written anywhere.
"""
import json
import logging
import os
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from .profiles import _SAFE

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CAL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPES = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.readonly"
STATE_TTL = 15 * 60

_SENDERS = ["instacart", "doordash", "ubereats", "grubhub", "costco", "walmart", "target", "wholefoods", "safeway",
            "traderjoes", "opentable", "resy", "yelp", "toasttab", "starbucks", "chipotle"]
_RESERVATION = re.compile(r"opentable|resy|yelp", re.I)
GMAIL_QUERY = f"newer_than:1y (from:({' OR '.join(_SENDERS)}) OR subject:(order OR receipt OR reservation))"
_NOISE = re.compile(r"shoes?|electronics?|software|password|security alert|application|job", re.I)
_FOOD = re.compile(r"\b(dinner|lunch|brunch|breakfast|restaurant|cafe|coffee|bbq|pizza|sushi|taqueria|grill|kitchen|"
                   r"boba|tea|bar)\b", re.I)

PAGE = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Connected</title>"
        "<body style='font-family:system-ui;max-width:34em;margin:2em auto;padding:0 16px'>"
        "<p>Connected. I'm reading your receipts and calendar now and will text you what I learned. "
        "You can close this tab.</p><p style='color:#555;font-size:.9em'>Read-only access. I read only subject lines, "
        "senders, dates and a short preview, never full emails. Nothing raw is stored, only the food facts I learn, "
        "in your memory log. The access token is discarded right after this import.</p></body>")


def config() -> dict | None:
    """None when the feature is off (no Google client configured)."""
    cid, secret = os.environ.get("GOOGLE_CLIENT_ID"), os.environ.get("GOOGLE_CLIENT_SECRET")
    if not (cid and secret):
        return None
    url = (os.environ.get("PUBLIC_URL") or "https://personal-agents-production-81468651.up.railway.app").rstrip("/")
    return {"id": cid, "secret": secret, "url": url, "redirect": url + "/connect/google/callback"}


def hint(sender: str) -> str:
    """The sentence appended to the onboarding texts; empty when the feature is off."""
    c = config()
    return (f" Or skip the question: connect Google and I'll learn from your receipts: "
            f"{c['url']}/connect/google?{urllib.parse.urlencode({'sender': sender})}") if c else ""


# ---- single-use OAuth state, on disk so it survives a restart between redirect and callback ----

def _states(data_dir, fn):
    p = Path(data_dir) / "connect" / "states.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    d = json.loads(p.read_text()) if p.exists() else {}
    now = time.time()
    d = {k: v for k, v in d.items() if v["exp"] > now}  # expired states are dropped on every touch
    out = fn(d)
    p.write_text(json.dumps(d))
    return out


_state_lock = threading.Lock()


def new_state(data_dir, sender: str) -> str:
    if not _SAFE.fullmatch(sender or ""):
        raise ValueError(f"unsafe sender id: {sender!r}")
    s = secrets.token_urlsafe(24)
    with _state_lock:
        _states(data_dir, lambda d: d.__setitem__(s, {"sender": sender, "exp": time.time() + STATE_TTL}))
    return s


def take_state(data_dir, state: str) -> str | None:
    """The sender for this state, deleting it; None when unknown or expired."""
    with _state_lock:
        v = _states(data_dir, lambda d: d.pop(state or "", None))
    return v["sender"] if v else None


def auth_url(c: dict, state: str) -> str:
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": c["id"], "redirect_uri": c["redirect"], "response_type": "code", "scope": SCOPES,
        "access_type": "online", "prompt": "consent", "state": state})


# ---- network: token exchange and a read-only GET fetcher ----

def exchange(c: dict, code: str) -> str:
    body = urllib.parse.urlencode({"code": code, "client_id": c["id"], "client_secret": c["secret"],
                                   "redirect_uri": c["redirect"], "grant_type": "authorization_code"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=body), timeout=20) as r:
        return json.loads(r.read())["access_token"]


def make_fetcher(token: str):
    def fetch(url: str, params: dict) -> dict:
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params, doseq=True),
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    return fetch


# ---- pure import: fetcher -> memory items ----

def gmail_items(fetch) -> list[dict]:
    ids = [m["id"] for m in fetch(GMAIL + "/messages", {"q": GMAIL_QUERY, "maxResults": 40}).get("messages", [])][:40]
    items = []
    for mid in ids:
        m = fetch(f"{GMAIL}/messages/{mid}", {"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"],
                                             "fields": "snippet,payload/headers"})  # never the body
        h = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
        subject, sender = h.get("subject", ""), h.get("from", "")
        if not subject or _NOISE.search(subject):
            continue
        name = parseaddr(sender)[0] or parseaddr(sender)[1] or sender
        item = {"text": f"{name}: {subject}. {(m.get('snippet') or '')[:200]}".strip(),
                "source": "message" if _RESERVATION.search(sender) else "receipt"}
        try:
            item["when"] = parsedate_to_datetime(h["date"]).isoformat()
        except (KeyError, TypeError, ValueError):
            pass
        items.append(item)
    return items


def calendar_items(fetch, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    events = fetch(CAL, {"timeMin": (now - timedelta(days=365)).isoformat(), "timeMax": now.isoformat(),
                         "singleEvents": "true", "maxResults": 100}).get("items", [])
    items = []
    for e in events[:100]:
        summary, where = e.get("summary") or "", e.get("location") or ""
        if not _FOOD.search(f"{summary} {where}"):
            continue
        item = {"text": f"Calendar: {summary}" + (f" at {where}" if where else ""), "source": "calendar"}
        if start := (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date"):
            item["when"] = start
        items.append(item)
    return items


def run_import(sender: str, fetch, memory, workflow, profiles) -> None:
    """Gmail + calendar -> memory, then one text to the sender. Never raises."""
    def send(text):
        workflow._update("outbox.json", [], lambda d: d.append({"sender": sender, "text": text}))
    try:
        items = gmail_items(fetch) + calendar_items(fetch)
        res = memory.add_many(sender, items) if items else {"profile": None, "added": [], "conflicts": []}
        p = res["profile"]
        facts = (p.allergens + p.restrictions + p.preferences)[:6] if p and res["added"] else []
        if profiles.get(sender) and profiles.pending(sender):
            profiles.set_pending(sender, False)  # the waiting first request is not run; they text it again
        if facts:
            n = len(res["conflicts"])
            text = (f"Connected. From your receipts and calendar I learned: {', '.join(facts)}."
                    + (f" {n} things I wasn't sure about, so I left them out." if n else "") + " Text me what you need.")
        else:
            text = ("Connected, but I didn't learn anything about your food from your receipts or calendar. "
                    "Text me what you need, and anything you can't have.")
        send(text)
    except Exception as e:
        log.exception("google import failed for %s", sender)
        reason = type(e).__name__ if not str(e) else str(e)[:80]
        try:
            send(f"I couldn't read your Google account ({reason}). No problem: just tell me anything you can't have.")
        except Exception:
            log.exception("could not enqueue the failure text")


def start(fn) -> None:  # tests replace this to run the import inline
    threading.Thread(target=fn, daemon=True).start()
