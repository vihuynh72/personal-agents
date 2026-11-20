"""Airbyte -> Cognee. For each connected person, Airbyte's Google Calendar connector (run through PyAirbyte, no
Airbyte server) reads the `freebusy` stream, and the busy blocks go to the shared Cognee dataset guest_availability.

PyAirbyte needs Python 3.12 and is not a project dependency, so run it in its own environment:
  set -a && . ./.env && set +a
  uv run --no-project --python 3.12 --with airbyte --with pydantic python -m tools.sync_calendars g1 [g4 ...]
"""
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

from tools import google_calendar as gc
from tools.availability import AIRBYTE, record_text, replace_record
from tools.cognee import Cognee

CONNECTOR = "source-google-calendar"


def _window(now: datetime) -> tuple[str, str]:
    # The connector asks Google for now-30d .. now+45d; claim one day less on each side so a slow run
    # never reports a window it did not read.
    f = "%Y-%m-%dT%H:%M:%SZ"
    return (now - timedelta(days=29)).strftime(f), (now + timedelta(days=44)).strftime(f)


def read_busy(refresh_token: str) -> list[dict]:
    """Busy blocks [{start, end}] of the person's primary calendar, through Airbyte's connector."""
    os.environ.setdefault("DO_NOT_TRACK", "1")  # no PyAirbyte usage telemetry
    import airbyte as ab  # only in the PyAirbyte environment; the rest of tools/ stays stdlib

    source = ab.get_source(CONNECTOR, install_if_missing=True, docker_image=False, config={
        "credentials": {"auth_type": "manual", "client_id": gc.env("GOOGLE_CLIENT_ID"),
                        "client_secret": gc.env("GOOGLE_CLIENT_SECRET"), "refresh_token": refresh_token},
        "calendarid": "primary"})
    source.select_streams(["calendarlist", "freebusy"])
    # A full read, not get_records: get_records on freebusy sometimes stops after starting and returns zero
    # records (seen live: 7 blocks, then 0, same token), which would read as "free". A full read was 7/7/7.
    # It needs a scratch cache; it lives in a temp dir that is deleted here, so Cognee stays the only store.
    scratch = tempfile.mkdtemp(prefix="gcal-")
    try:
        result = source.read(cache=ab.new_local_cache(cache_name="gcal", cache_dir=scratch, cleanup=True),
                             force_full_refresh=True)
        calendars = list(result["calendarlist"])
        busy = list(result["freebusy"])
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    # Every account has a primary calendar, so an empty calendar list means Google refused the read (bad, revoked
    # or under-scoped token): raise, and the person's availability is left as it was. (The connector's own check()
    # reads the `colors` stream, which needs a wider scope than we ask for.)
    primary = next((c["id"] for c in calendars if c.get("primary")), None)
    if primary is None:
        raise RuntimeError("Airbyte could not read this person's calendar list; access failed or was revoked")
    # freebusy covers every calendar on the list (holidays, calendars shared by others); only the person's own
    # primary calendar says whether they are busy.
    return [{"start": _iso(r["start"]), "end": _iso(r["end"])} for r in busy if r["calendar_id"] == primary]


def _iso(v) -> str:
    """The cache hands timestamps back as datetimes (UTC when no zone is attached); store ISO text with a zone."""
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return str(v)


def sync_person(person_id: str, name: str, cognee: Cognee | None = None, reader=read_busy,
                now: datetime | None = None) -> int:
    """Read one person through Airbyte and store the result in Cognee. Returns the number of busy blocks."""
    token = gc.refresh_token(person_id)
    if token is None:
        raise LookupError(f"{person_id} has not connected a calendar")
    now = now or datetime.now(timezone.utc)
    busy = reader(token)
    text = record_text(person_id, name, busy, _window(now), AIRBYTE, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    replace_record(cognee or Cognee(), person_id, text)
    return len(busy)


if __name__ == "__main__":
    from tools.real import load_profiles

    names = {p.id: p.name for p in load_profiles().values()}
    for pid in sys.argv[1:]:
        n = sync_person(pid, names.get(pid, pid))
        print(f"{pid}: synced {n} busy block(s) through Airbyte into Cognee guest_availability")
