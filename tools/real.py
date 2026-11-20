"""Ketki's tools/ (docs/agent-graph.md, "Ketki's piece"). F2: guest profiles.

Source: the team's shared Cognee workspace (dataset `guest_profiles`, filled by `python -m tools.load_cognee`)
when COGNEE_URL and COGNEE_API_KEY are set; tools/profiles.json otherwise, or if Cognee fails or lacks the guest.
Synthetic demo guests from "docs/Product Brief .md": one vegan, one no spicy food, one no mushrooms, three with none.

Only contracts/ is imported, never agent/ ("tools/ never calls agent/"). Every other Tools method is still
FakeTools until it is built here, so Vi combines this with the real search and Stripe in agent/api.py:

    class AppTools(BrightDataTools, RealTools): pass
"""
import json
import logging
import os
import time
from pathlib import Path

from contracts.fixtures import FakeTools
from contracts.models import GuestProfile

log = logging.getLogger(__name__)

PROFILES = Path(__file__).parent / "profiles.json"
TTL = 30  # seconds; the workflow asks for every guest at once, so read Cognee once per burst, not once per guest


def load_profiles(path: Path = PROFILES) -> dict[str, GuestProfile]:
    profiles = [GuestProfile(**d) for d in json.loads(path.read_text())]
    by_id = {p.id: p for p in profiles}
    if len(by_id) != len(profiles):
        raise ValueError(f"duplicate guest id in {path}")
    return by_id


class RealTools(FakeTools):
    # No __init__ on purpose: StripeTools.__init__ does not call super(), so in the combined class above
    # an __init__ here would never run. State lives in class attributes set on first use.
    profiles_path = PROFILES
    _cognee_cache: tuple[float, dict[str, GuestProfile]] | None = None

    def _from_cognee(self) -> dict[str, GuestProfile]:
        if not (os.environ.get("COGNEE_URL") and os.environ.get("COGNEE_API_KEY")):
            return {}
        cached = RealTools._cognee_cache  # on the class, so every instance and subclass shares one cache
        if cached and time.monotonic() - cached[0] < TTL:
            return cached[1]
        from tools.cognee import Cognee
        try:
            found = Cognee().profiles()
        except Exception as e:  # Cognee down or slow: the demo continues on the file copy
            log.warning("Cognee profile read failed, using %s: %r", self.profiles_path.name, e)
            found = {}
        RealTools._cognee_cache = (time.monotonic(), found)
        return found

    def get_profile(self, guest_id: str) -> GuestProfile:  # F2
        if p := self._from_cognee().get(guest_id):
            return p
        # File read on every call (six small records) so an edit shows on the next run without a restart.
        profiles = load_profiles(self.profiles_path)
        if guest_id not in profiles:
            raise KeyError(guest_id)  # same as FakeTools; agent/api.py turns it into a 404
        return profiles[guest_id]
