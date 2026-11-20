"""Google sign-in for calendar access (the Accept step at onboarding). Stdlib only.

  1. connect_url(person_id)  -> link to Google's consent screen
  2. backend callback        -> finish_connect(code, state) saves that person's refresh token
  3. tools/sync_calendars.py -> Airbyte's Google Calendar connector uses the token to read free/busy into Cognee

Scopes are what Airbyte's `freebusy` stream needs (checked live): free/busy, plus calendar-list and calendar
metadata to find the calendars to query. No event titles, descriptions or attendees can be read with them.

The refresh token is a credential, not memory, so it stays out of the shared Cognee graph: it is kept in
.data/calendar_tokens/<person_id>.json on the machine that runs the sync (.data/ is gitignored).
Env: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI.
"""
import hashlib
import hmac
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/calendar.freebusy",
          "https://www.googleapis.com/auth/calendar.calendarlist.readonly",  # Airbyte's freebusy partitions on calendarList
          "https://www.googleapis.com/auth/calendar.calendars.readonly"]
TOKENS = Path(".data/calendar_tokens")
_SAFE = re.compile(r"[A-Za-z0-9+@_-][A-Za-z0-9+@._-]{0,63}")  # same id rule as agent/profiles.py: no path tricks


def _http(method: str, url: str, headers: dict, body: bytes | None, timeout: float = 20) -> dict:
    """The one network call; tests monkeypatch it. Non-2xx raises urllib.error.HTTPError."""
    req = urllib.request.Request(url, method=method, headers=headers, data=body)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"{name} is not set")
    return v


def check_id(person_id: str) -> str:
    if not _SAFE.fullmatch(person_id or ""):
        raise ValueError(f"unsafe person id: {person_id!r}")
    return person_id


def _sign(person_id: str) -> str:
    return hmac.new(env("GOOGLE_CLIENT_SECRET").encode(), person_id.encode(), hashlib.sha256).hexdigest()[:32]


def _token_path(person_id: str) -> Path:
    return TOKENS / f"{check_id(person_id)}.json"


def connect_url(person_id: str) -> str:
    """The Accept link. `state` is signed so a callback can only connect the person the link was made for."""
    state = f"{check_id(person_id)}.{_sign(person_id)}"
    return AUTH + "?" + urllib.parse.urlencode({
        "client_id": env("GOOGLE_CLIENT_ID"), "redirect_uri": env("GOOGLE_REDIRECT_URI"),
        "response_type": "code", "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
        "include_granted_scopes": "true", "state": state})


def finish_connect(code: str, state: str) -> str:
    """Called by the OAuth callback. Returns the connected person_id."""
    person_id, _, sig = state.rpartition(".")
    if not person_id or not hmac.compare_digest(sig, _sign(check_id(person_id))):
        raise ValueError("bad state")
    out = _http("POST", TOKEN, {"Content-Type": "application/x-www-form-urlencoded"}, urllib.parse.urlencode({
        "code": code, "client_id": env("GOOGLE_CLIENT_ID"), "client_secret": env("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": env("GOOGLE_REDIRECT_URI"), "grant_type": "authorization_code"}).encode())
    if not out.get("refresh_token"):
        raise RuntimeError("Google returned no refresh token")
    missing = set(SCOPES) - set(out.get("scope", " ".join(SCOPES)).split())
    if missing:  # Google lets people untick a permission; without it Airbyte's sync would fail later
        raise PermissionError(f"not all calendar permissions were granted: {sorted(missing)}")
    TOKENS.mkdir(parents=True, exist_ok=True)
    p = _token_path(person_id)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"refresh_token": out["refresh_token"]}))  # access tokens expire; never stored
    tmp.replace(p)
    return person_id


def refresh_token(person_id: str) -> str | None:
    p = _token_path(person_id)
    return json.loads(p.read_text())["refresh_token"] if p.exists() else None


def is_connected(person_id: str) -> bool:
    return _SAFE.fullmatch(person_id or "") is not None and _token_path(person_id).exists()


def disconnect(person_id: str) -> None:
    """Decline after accepting: forget the token, so nothing can read their calendar any more."""
    _token_path(person_id).unlink(missing_ok=True)
