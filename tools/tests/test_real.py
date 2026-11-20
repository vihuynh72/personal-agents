import json

import pytest

from contracts.models import GuestProfile
from tools.real import PROFILES, RealTools, load_profiles

GUESTS = ["g1", "g2", "g3", "g4", "g5", "g6"]


def test_demo_guests_match_the_product_brief():
    profiles = load_profiles()
    assert sorted(profiles) == GUESTS  # six diners
    by_restriction = sorted(r for p in profiles.values() for r in p.restrictions)
    assert by_restriction == ["no mushrooms", "no spicy food", "vegan"]
    assert sum(1 for p in profiles.values() if not p.restrictions and not p.allergens) == 3


def test_get_profile_returns_the_contract_shape():
    ketki = RealTools().get_profile("g1")
    assert isinstance(ketki, GuestProfile)
    assert ketki.name == "Ketki" and ketki.restrictions == ["vegan"]


def test_unknown_guest_raises_key_error():
    with pytest.raises(KeyError):
        RealTools().get_profile("nobody")


def test_duplicate_ids_are_rejected(tmp_path):
    f = tmp_path / "p.json"
    rows = json.loads(PROFILES.read_text())
    f.write_text(json.dumps(rows + [rows[0]]))
    with pytest.raises(ValueError):
        load_profiles(f)


def test_edits_show_without_restart(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps([{"id": "g1", "name": "Alex"}]))
    tools = RealTools()
    tools.profiles_path = f
    assert tools.get_profile("g1").restrictions == []
    f.write_text(json.dumps([{"id": "g1", "name": "Alex", "restrictions": ["vegan"]}]))
    assert tools.get_profile("g1").restrictions == ["vegan"]


def test_combined_with_vi_search_and_stripe(monkeypatch, tmp_path):
    """The swap Vi makes in agent/api.py: real profiles flow into the agent's ingredient check."""
    from agent.llm import FakeLLM
    from agent.products import BrightDataTools
    from agent.workflow import Workflow

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)

    class AppTools(BrightDataTools, RealTools):
        pass

    wf = Workflow(AppTools(), FakeLLM(), data_dir=str(tmp_path))
    g = wf.start("Host", "dinner at my place Saturday for six", "1 Main St", GUESTS)
    assert g.status == "awaiting_plan_approval"
    f2 = [e for e in wf.audit(g.id) if e.node_id == "F2"]
    assert f2 and "Ketki" in json.dumps([e.model_dump(mode="json") for e in f2])
