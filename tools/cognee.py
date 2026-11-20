"""Guest profiles in the team's shared Cognee workspace (dataset `guest_profiles`). Stdlib only.

Each profile is one text item: a first line `GUEST_PROFILE {json}` that get_profile reads back exactly, then one
plain sentence so Cognee's graph (cognify) links the person to their restrictions for agent memory search.
"""
import json
import os
import urllib.request

from contracts.models import GuestProfile

DATASET = "guest_profiles"
TAG = "GUEST_PROFILE "


def _http(method: str, url: str, headers: dict, body: dict | None, timeout: float):
    """The one network call; tests monkeypatch it. Non-2xx raises urllib.error.HTTPError."""
    req = urllib.request.Request(url, method=method, headers=headers,
                                 data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode(errors="replace")
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return raw  # /raw returns the stored text itself


def to_text(p: GuestProfile) -> str:
    said = "; ".join([f"restrictions: {', '.join(p.restrictions)}"] * bool(p.restrictions) +
                     [f"allergens: {', '.join(p.allergens)}"] * bool(p.allergens)) or "no dietary restrictions"
    return f"{TAG}{p.model_dump_json()}\n{p.name} (guest id {p.id}) has {said}."


def from_text(text: str) -> GuestProfile | None:
    first = text.lstrip().split("\n", 1)[0]
    return GuestProfile.model_validate_json(first[len(TAG):]) if first.startswith(TAG) else None


class Cognee:
    def __init__(self):
        self.url = (os.environ.get("COGNEE_URL") or "").rstrip("/")
        self.key = os.environ.get("COGNEE_API_KEY")
        if not (self.url and self.key):
            raise RuntimeError("COGNEE_URL and COGNEE_API_KEY must be set")

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float = 30):
        return _http(method, self.url + "/api/v1" + path,
                     {"X-Api-Key": self.key, "Content-Type": "application/json"}, body, timeout)

    def dataset_id(self, create: bool = False) -> str | None:
        if create:  # idempotent: returns the existing dataset when the name is taken
            return self._call("POST", "/datasets/", {"name": DATASET})["id"]
        return next((d["id"] for d in self._call("GET", "/datasets/") if d["name"] == DATASET), None)

    def profiles(self) -> dict[str, GuestProfile]:
        """Every profile in the dataset. If an id appears twice, the newest item wins."""
        ds = self.dataset_id()
        if ds is None:
            return {}
        items = sorted(self._call("GET", f"/datasets/{ds}/data?limit=500"), key=lambda d: d.get("createdAt") or "")
        out = {}
        for it in items:
            if p := from_text(self._call("GET", f"/datasets/{ds}/data/{it['id']}/raw")):
                out[p.id] = p
        return out

    def replace_profiles(self, profiles: list[GuestProfile]) -> str:
        """Empty this one dataset, then add every profile and start cognify. Touches no other dataset."""
        ds = self.dataset_id(create=True)
        for it in self._call("GET", f"/datasets/{ds}/data?limit=500"):
            self._call("DELETE", f"/datasets/{ds}/data/{it['id']}")
        self._call("POST", "/add_text", {"textData": [to_text(p) for p in profiles], "datasetId": ds}, timeout=120)
        self._call("POST", "/cognify", {"datasetIds": [ds], "runInBackground": True}, timeout=60)
        return ds
