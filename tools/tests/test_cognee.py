import pytest

from contracts.models import GuestProfile
from tools import cognee
from tools.cognee import Cognee, from_text, to_text
from tools.real import RealTools, load_profiles


class FakeCognee:
    """In-memory stand-in for the Cognee HTTP API, answering only the paths tools/cognee.py calls."""

    def __init__(self):
        self.datasets = [{"id": "other", "name": "agent_sessions"}]  # someone else's dataset; must stay untouched
        self.data: dict[str, list[dict]] = {"other": [{"id": "x", "createdAt": "1", "text": "not ours"}]}
        self.calls = []
        self.n = 0

    def __call__(self, method, url, headers, body, timeout):
        assert headers["X-Api-Key"] == "k"
        path = url.split("/api/v1", 1)[1].split("?")[0]
        self.calls.append((method, path))
        if (method, path) == ("GET", "/datasets/"):
            return self.datasets
        if (method, path) == ("POST", "/datasets/"):
            ds = next((d for d in self.datasets if d["name"] == body["name"]), None)
            if not ds:
                ds = {"id": body["name"], "name": body["name"]}
                self.datasets.append(ds)
                self.data[ds["id"]] = []
            return ds
        if (method, path) == ("POST", "/add_text"):
            for t in body["textData"]:
                self.n += 1
                self.data[body["datasetId"]].append({"id": f"d{self.n}", "createdAt": f"{self.n:04}", "text": t})
            return {}
        if (method, path) == ("POST", "/cognify"):
            return {"pipeline_run_id": "r"}
        parts = path.strip("/").split("/")  # datasets/<ds>/data[/<id>[/raw]]
        ds = parts[1]
        if method == "GET" and len(parts) == 3:
            return [{k: v for k, v in d.items() if k != "text"} for d in self.data[ds]]
        if method == "GET" and parts[-1] == "raw":
            return next(d["text"] for d in self.data[ds] if d["id"] == parts[3])
        if method == "DELETE":
            self.data[ds] = [d for d in self.data[ds] if d["id"] != parts[3]]
            return {}
        raise AssertionError(f"unexpected call {method} {path}")


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("COGNEE_URL", "https://cognee.test/")
    monkeypatch.setenv("COGNEE_API_KEY", "k")
    f = FakeCognee()
    monkeypatch.setattr(cognee, "_http", f)
    return f


def test_text_round_trip():
    p = GuestProfile(id="g1", name="Ketki", restrictions=["vegan"], allergens=["peanut"])
    text = to_text(p)
    assert from_text(text) == p
    assert "Ketki (guest id g1) has restrictions: vegan; allergens: peanut." in text
    assert from_text("some other memory") is None


def test_load_then_read_back(fake):
    profiles = list(load_profiles().values())
    Cognee().replace_profiles(profiles)
    assert Cognee().profiles() == {p.id: p for p in profiles}
    assert ("POST", "/cognify") in fake.calls
    assert fake.data["other"] == [{"id": "x", "createdAt": "1", "text": "not ours"}]


def test_reload_replaces_instead_of_duplicating(fake):
    profiles = list(load_profiles().values())
    Cognee().replace_profiles(profiles)
    Cognee().replace_profiles(profiles)
    assert len(fake.data["guest_profiles"]) == len(profiles)


def test_newest_item_wins_for_the_same_id(fake):
    ds = Cognee().dataset_id(create=True)
    fake.data[ds] += [{"id": "a", "createdAt": "0001", "text": to_text(GuestProfile(id="g1", name="Ketki"))},
                      {"id": "b", "createdAt": "0002",
                       "text": to_text(GuestProfile(id="g1", name="Ketki", restrictions=["vegan"]))}]
    assert Cognee().profiles()["g1"].restrictions == ["vegan"]


def test_get_profile_prefers_cognee(fake):
    Cognee().replace_profiles([GuestProfile(id="g1", name="Ketki", restrictions=["vegan", "halal"])])
    assert RealTools().get_profile("g1").restrictions == ["vegan", "halal"]  # Cognee's copy, not the file's
    assert RealTools().get_profile("g4").name == "Ryan"  # not in Cognee: falls back to the file


def test_reads_cognee_once_per_burst(fake):
    Cognee().replace_profiles(list(load_profiles().values()))
    fake.calls.clear()
    for g in ["g1", "g2", "g3", "g4", "g5", "g6"]:
        RealTools().get_profile(g)
    assert fake.calls.count(("GET", "/datasets/")) == 1


def test_cognee_down_falls_back_to_file(monkeypatch):
    monkeypatch.setenv("COGNEE_URL", "https://cognee.test")
    monkeypatch.setenv("COGNEE_API_KEY", "k")

    def down(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(cognee, "_http", down)
    assert RealTools().get_profile("g1").name == "Ketki"
