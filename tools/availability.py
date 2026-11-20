"""F4 availability, read from the shared Cognee dataset `guest_availability`. Stdlib only, so the backend can use it.

Records are written by tools/sync_calendars.py (Airbyte's Google Calendar connector, one record per connected
person) and by tools/load_cognee.py (labelled simulated records for the synthetic demo guests).
For a time window each person is:
  free     a record covers the window and has no busy block overlapping it
  busy     a busy block overlaps the window
  pending  no record (declined, never connected, never synced), the record does not cover the window, or a
           real calendar has not synced for MAX_AGE (the agent's loop keeps it fresh; a stalled loop must not
           leave an old "free" standing)
Pending never means free. Only busy intervals are stored: no event titles or details exist anywhere in this flow.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from tools.cognee import Cognee, tagged

DATASET = "guest_availability"
TAG = "AVAILABILITY "
AIRBYTE = "airbyte/source-google-calendar"
SIMULATED = "simulated"
MAX_AGE = timedelta(minutes=30)  # real calendars only; simulated demo data does not go stale

Status = Literal["free", "busy", "pending"]


@dataclass
class Answer:
    status: Status
    source: str | None = None  # AIRBYTE, SIMULATED, or None when pending without a record
    synced_at: str | None = None


def record_text(person_id: str, name: str, busy: list[dict], window: tuple[str, str], source: str,
                synced_at: str) -> str:
    rec = {"person_id": person_id, "busy": busy, "window": list(window), "source": source, "synced_at": synced_at}
    said = (f"busy {len(busy)} time(s) between {window[0]} and {window[1]}" if busy
            else f"free between {window[0]} and {window[1]}")
    label = " (simulated demo data)" if source == SIMULATED else ""
    return f"{TAG}{json.dumps(rec)}\n{name} (guest id {person_id}) calendar{label}: {said}."


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def decide(rec: dict | None, start: datetime, end: datetime, now: datetime | None = None) -> Answer:
    if rec is None:
        return Answer("pending")
    now = now or datetime.now(timezone.utc)
    if rec["source"] == AIRBYTE and now - _t(rec["synced_at"]) > MAX_AGE:
        return Answer("pending", rec["source"], rec["synced_at"])
    w0, w1 = (_t(x) for x in rec["window"])
    if not (w0 <= start and end <= w1):
        return Answer("pending", rec["source"], rec["synced_at"])
    busy = any(_t(b["start"]) < end and start < _t(b["end"]) for b in rec["busy"])
    return Answer("busy" if busy else "free", rec["source"], rec["synced_at"])


def records(cognee: Cognee | None = None) -> dict[str, tuple[str, dict]]:
    """person_id -> (data_id, record), newest record per person."""
    out = {}
    for data_id, text in (cognee or Cognee()).items(DATASET):
        if rec := tagged(TAG, text):
            out[rec["person_id"]] = (data_id, rec)
    return out


def availability(person_ids: list[str], start: datetime, end: datetime,
                 cognee: Cognee | None = None, now: datetime | None = None) -> dict[str, Answer]:
    """Free/busy/pending per person for [start, end). Times must carry a timezone."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end need a timezone")
    if end <= start:
        raise ValueError("end must be after start")
    recs = records(cognee)
    return {pid: decide(recs.get(pid, (None, None))[1], start, end, now) for pid in person_ids}


def replace_record(cognee: Cognee, person_id: str, text: str) -> None:
    """Add the new record first, then drop older ones for this person, so a reader never sees nobody."""
    old = [d for d, t in cognee.items(DATASET) if (r := tagged(TAG, t)) and r["person_id"] == person_id]
    cognee.add(DATASET, [text])
    cognee.delete(DATASET, old)


def forget(cognee: Cognee, person_id: str) -> None:
    """On disconnect: remove this person's availability from shared memory."""
    cognee.delete(DATASET, [d for d, t in cognee.items(DATASET) if (r := tagged(TAG, t)) and r["person_id"] == person_id])
