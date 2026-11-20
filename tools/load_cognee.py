"""Push tools/profiles.json into the shared Cognee dataset `guest_profiles`. Run after editing the file:
set -a && . ./.env && set +a && uv run python -m tools.load_cognee
"""
from tools.cognee import Cognee
from tools.real import load_profiles

if __name__ == "__main__":
    profiles = list(load_profiles().values())
    cognee = Cognee()
    ds = cognee.replace_profiles(profiles)
    back = cognee.profiles()
    assert back == {p.id: p for p in profiles}, "Cognee did not return the same profiles"
    print(f"Loaded {len(back)} profiles into Cognee dataset guest_profiles ({ds}); read back and matched.")
