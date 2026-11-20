"""The team's shared Cognee workspace, over its HTTP API. Stdlib only.

Datasets owned by tools/: `guest_profiles` (F2) and `guest_availability` (F4, filled by tools/sync_calendars.py).
Each record is one text item: a first line `<TAG> {json}` that is read back exactly, then one plain sentence so
Cognee's graph (cognify) can link people to facts for agent memory search.
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


def tagged(tag: str, text: str) -> dict | None:
    """The JSON on a `<tag> {json}` first line, or None for any other item."""
    first = text.lstrip().split("\n", 1)[0]
    return json.loads(first[len(tag):]) if first.startswith(tag) else None


class Cognee:
    def __init__(self):
        self.url = (os.environ.get("COGNEE_URL") or "").rstrip("/")
        self.key = os.environ.get("COGNEE_API_KEY")
        if not (self.url and self.key):
            raise RuntimeError("COGNEE_URL and COGNEE_API_KEY must be set")

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float = 30):
        return _http(method, self.url + "/api/v1" + path,
                     {"X-Api-Key": self.key, "Content-Type": "application/json"}, body, timeout)

    # ---- any dataset by name ----

    def dataset_id(self, create: bool = False, name: str = DATASET) -> str | None:
        if create:  # idempotent: returns the existing dataset when the name is taken
            return self._call("POST", "/datasets/", {"name": name})["id"]
        return next((d["id"] for d in self._call("GET", "/datasets/") if d["name"] == name), None)

    def items(self, name: str) -> list[tuple[str, str]]:
        """(data_id, text) for every item in the dataset, oldest first."""
        ds = self.dataset_id(name=name)
        if ds is None:
            return []
        rows = sorted(self._call("GET", f"/datasets/{ds}/data?limit=500"), key=lambda d: d.get("createdAt") or "")
        return [(r["id"], self._call("GET", f"/datasets/{ds}/data/{r['id']}/raw")) for r in rows]

    def add(self, name: str, texts: list[str], cognify: bool = True) -> str:
        ds = self.dataset_id(create=True, name=name)
        self._call("POST", "/add_text", {"textData": texts, "datasetId": ds}, timeout=120)
        if cognify:
            self._call("POST", "/cognify", {"datasetIds": [ds], "runInBackground": True}, timeout=60)
        return ds

    def delete(self, name: str, data_ids: list[str]) -> None:
        ds = self.dataset_id(name=name)
        for d in data_ids if ds else []:
            self._call("DELETE", f"/datasets/{ds}/data/{d}")

    # ---- guest profiles ----

    def profiles(self) -> dict[str, GuestProfile]:
        """Every profile in the dataset. If an id appears twice, the newest item wins."""
        out = {}
        for _, text in self.items(DATASET):
            if p := from_text(text):
                out[p.id] = p
        return out

    def replace_profiles(self, profiles: list[GuestProfile]) -> str:
        """Empty this one dataset, then add every profile and start cognify. Touches no other dataset."""
        self.dataset_id(create=True)
        self.delete(DATASET, [d for d, _ in self.items(DATASET)])
        return self.add(DATASET, [to_text(p) for p in profiles])
