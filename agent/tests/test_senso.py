import pytest

from agent import senso as senso_mod
from agent.llm import FakeLLM
from agent.senso import Senso
from agent.workflow import Workflow
from contracts.fixtures import FakeTools

GUESTS = ["g1", "g2", "g3", "g4"]


class FakeSenso:
    def __init__(self, hits=True, claims=()):
        self.hits, self.claims, self.checks = hits, list(claims), []

    def search(self, query, limit=3):
        if not self.hits:
            return []
        return [{"content_id": "c-1", "kb_node_id": "n-1", "version_id": "v-1", "rank": 1, "score": 0.9,
                 "chunk_text": "x" * 300}]

    def check(self, text, question):
        self.checks.append((text, question))
        return {"id": "run-1", "status": "completed", "claims": self.claims}


class BrokenSenso:
    def search(self, query, limit=3):
        raise RuntimeError("search down")

    def check(self, text, question):
        raise RuntimeError("check down")


def _run(tmp_path, senso):
    wf = Workflow(FakeTools(), FakeLLM(), data_dir=str(tmp_path), senso=senso)
    g = wf.start("Vi", "dinner at my place Saturday for six", "1 Main St", GUESTS)
    g = wf.approve_plan(g.id)
    return g, wf.audit(g.id)


def _claim(text, verdict):
    return {"claim_text": text, "source_text": text, "verdict": verdict, "reasoning": "r"}


def test_f6_audit_has_senso_context_and_trimmed_chunk(tmp_path):
    g, audit = _run(tmp_path, FakeSenso())
    f6 = [e for e in audit if e.node_id == "F6"]
    assert f6 and all("senso:content_id=c-1 version=v-1 rank=1 score=0.9" in e.context_used for e in f6)
    assert all(e.inputs["senso"] == "x" * 200 for e in f6)
    f10 = [e for e in audit if e.node_id == "F10"]
    assert len(f10) == 1 and f10[0].context_used == ["senso:eval_run_id=run-1"]
    assert f10[0].inputs["question"] == "dinner at my place Saturday for six"
    assert "Spaghetti from StoreA costs $1.98" in f10[0].inputs["statement"]
    assert "Spaghetti does not contain egg." in f10[0].inputs["statement"]


def test_no_context_marks_unknown_but_keeps_item(tmp_path):
    g, audit = _run(tmp_path, FakeSenso(hits=False))
    assert g.cart.items and all(i.status == "unknown" for i in g.cart.items)
    assert all("could not confirm" in " ".join(i.alerts) for i in g.cart.items)
    assert all("no supporting context in Senso" in e.decision for e in audit if e.node_id == "F6")


def test_conflict_removes_item_before_checkout(tmp_path):
    s = FakeSenso(claims=[_claim("Spaghetti from StoreA costs $1.98 and contains durum wheat semolina.", "conflict")])
    g, audit = _run(tmp_path, s)
    assert "Spaghetti" not in [i.product.name for i in g.cart.items] and g.cart.items
    f10 = next(e for e in audit if e.node_id == "F10")
    assert "Removed before checkout" in f10.decision and "Spaghetti" in f10.decision
    f7 = next(e for e in audit if e.node_id == "F7")
    assert len(f7.inputs["items"]) == len(g.cart.items)
    assert audit.index(f10) < audit.index(f7)


def test_unsupported_marks_unknown(tmp_path):
    s = FakeSenso(claims=[_claim("Marinara Sauce from StoreB costs $2.49.", "unsupported")])
    g, audit = _run(tmp_path, s)
    item = next(i for i in g.cart.items if i.product.name == "Marinara Sauce")
    assert item.status == "unknown" and item.alerts
    assert next(i for i in g.cart.items if i.product.name == "Spaghetti").status == "pass"


def test_senso_errors_are_audited_and_do_not_break_the_run(tmp_path):
    g, audit = _run(tmp_path, BrokenSenso())
    assert g.status == "awaiting_payment" and g.checkout_url
    assert all(i.status == "pass" for i in g.cart.items)  # a failed Senso step changes nothing
    failed = [e.decision for e in audit if e.node_id == "F10"]
    assert any("search failed" in d for d in failed) and any("fact-check failed" in d for d in failed)


def test_pending_check_does_not_block(tmp_path):
    class Pending(FakeSenso):
        def check(self, text, question):
            return {"id": "run-2", "status": "pending", "claims": []}

    g, audit = _run(tmp_path, Pending())
    assert g.status == "awaiting_payment"
    assert "pending" in next(e for e in audit if e.node_id == "F10").decision


def test_without_senso_no_senso_entries(tmp_path):
    g, audit = _run(tmp_path, None)
    assert not [e for e in audit if e.node_id == "F10"]
    assert not any("senso" in str(e.inputs) + str(e.context_used) + e.decision.lower() for e in audit)


# ---- Senso request building ----

@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake(method, url, headers, body, timeout):
        calls.append((method, url, headers, body, timeout))
        return fake.reply

    fake.reply = (200, {})
    monkeypatch.setattr(senso_mod, "_http", fake)
    monkeypatch.setenv("SENSO_API_KEY", "k-test")
    return calls, fake


def test_requires_key(monkeypatch):
    monkeypatch.delenv("SENSO_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        Senso()


def test_add_document_request(sent):
    calls, fake = sent
    fake.reply = (202, {"id": "c1", "kb_node_id": "n1", "processing_status": "pending"})
    assert Senso().add_document("T", "body")["id"] == "c1"
    method, url, headers, body, timeout = calls[0]
    assert (method, url) == ("POST", "https://apiv2.senso.ai/api/v1/org/kb/raw")
    assert headers["X-API-Key"] == "k-test" and body == {"title": "T", "text": "body"} and timeout


def test_search_request_and_results(sent):
    calls, fake = sent
    fake.reply = (200, {"results": [{"content_id": "c", "rank": 1}]})
    assert Senso().search("oat milk", limit=2) == [{"content_id": "c", "rank": 1}]
    _, url, headers, body, timeout = calls[0]
    assert url == "https://apiv2.senso.ai/api/v1/org/search/context" and headers["X-API-Key"] == "k-test"
    assert body == {"query": "oat milk", "max_results": 2, "search_type": "hybrid"} and timeout


def test_check_request_finished_and_pending(sent):
    calls, fake = sent
    fake.reply = (200, {"eval_run_id": "r1", "status": "completed", "accuracy_pct": 50, "band": "red",
                        "claims": [{"claim_text": "a", "source_text": "a.", "verdict": "conflict", "reasoning": "why", "x": 1}]})
    out = Senso().check("text", "question")
    _, url, headers, body, timeout = calls[0]
    assert url == "https://apiv2.senso.ai/api/v1/org/evals/text" and headers["X-API-Key"] == "k-test"
    assert body == {"text": "text", "question": "question", "author": "ai_assistant", "wait": True} and timeout == 60
    assert out["id"] == "r1" and out["status"] == "completed"
    assert out["claims"] == [{"claim_text": "a", "source_text": "a.", "verdict": "conflict", "reasoning": "why"}]
    fake.reply = (202, {"eval_run_id": "r2", "status": "running"})
    assert Senso().check("t", "q") == {"id": "r2", "status": "pending", "accuracy_pct": None, "band": None, "claims": []}
