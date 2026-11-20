"""Day-0 import: post a person's past messages, receipts and calendar entries to the agent's memory.
Run: uv run python scripts/import_history.py <person_id> [file]   (API_URL defaults to the Railway deployment)"""
import json
import os
import sys
import urllib.request

API = os.environ.get("API_URL", "https://personal-agents-production-81468651.up.railway.app").rstrip("/")


def main(person_id: str, path: str = "demo/sample_history.json") -> None:
    body = json.dumps({"items": json.load(open(path))["items"]}).encode()
    req = urllib.request.Request(f"{API}/profiles/{person_id}/import", data=body,
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.load(r)
    print(f"facts added: {out['added']}")
    print("profile:", json.dumps(out["profile"], indent=2))
    for c in out["conflicts"]:
        flag = " [needs confirmation]" if c.get("needs_confirmation") else ""
        print(f"- {c['value']}: {c['rule']}{flag}\n    kept:       {c['kept']['evidence']}"
              f"\n    superseded: {c['superseded']['evidence']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
