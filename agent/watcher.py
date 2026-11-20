"""Notices Stripe payments without a webhook: polls every awaiting_payment gathering and fulfils it once paid."""
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

MAX_AGE = timedelta(hours=24)  # an unpaid checkout older than this is no longer polled


def tick(wf) -> None:
    """One pass. Never raises; mark_paid's status check and lock stop a double fire."""
    cutoff = datetime.now(timezone.utc) - MAX_AGE
    try:
        gids = wf.ids("awaiting_payment")
    except Exception:
        log.exception("watcher: could not list gatherings")
        return
    for gid in gids:
        try:
            audit = wf.audit(gid)
            if audit and audit[0].time < cutoff:
                continue
            if wf.check_paid(gid):
                log.info("watcher: %s paid and fulfilled", gid)
        except Exception:
            log.exception("watcher: %s failed; will retry next tick", gid)
    try:
        wf.send_followups()  # delayed post-order follow-ups (FEEDBACK_DELAY_SECONDS)
    except Exception:
        log.exception("watcher: follow-ups failed; will retry next tick")


def start(wf, interval: float | None = None) -> threading.Event:
    """Start the daemon thread; set the returned event to stop it."""
    interval = float(os.environ.get("PAY_POLL_SECONDS", "5")) if interval is None else interval
    stop = threading.Event()

    def loop():
        while not stop.wait(interval):
            tick(wf)

    threading.Thread(target=loop, name="pay-watcher", daemon=True).start()
    return stop
