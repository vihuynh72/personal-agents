"""Push tools/profiles.json and the simulated demo availability into the shared Cognee workspace. Run after editing:
set -a && . ./.env && set +a && uv run python -m tools.load_cognee

Simulated availability covers only synthetic guests and follows the story in web/src/App.tsx (Sam free evenings,
Jamie busy Saturday, Marco free, Lee away until Sunday). Real people get availability only by connecting Google.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from tools.availability import SIMULATED, record_text, replace_record
from tools.cognee import Cognee
from tools.real import load_profiles

SIM = Path(__file__).parent / "availability_simulated.json"

if __name__ == "__main__":
    profiles = load_profiles()
    cognee = Cognee()
    ds = cognee.replace_profiles(list(profiles.values()))
    back = cognee.profiles()
    assert back == profiles, "Cognee did not return the same profiles"
    print(f"Loaded {len(back)} profiles into Cognee dataset guest_profiles ({ds}); read back and matched.")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for r in json.loads(SIM.read_text()):
        name = profiles[r["person_id"]].name
        replace_record(cognee, r["person_id"],
                       record_text(r["person_id"], name, r["busy"], tuple(r["window"]), SIMULATED, now))
    print(f"Loaded simulated availability for {len(json.loads(SIM.read_text()))} synthetic guests "
          "into guest_availability.")
