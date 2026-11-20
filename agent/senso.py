"""Senso Context Layer over its HTTP API (spec: https://docs.senso.ai/specs/sdk-api.yaml). Stdlib only."""
import json
import os
import urllib.request

BASE = "https://apiv2.senso.ai/api/v1"
_DONE = {"completed", "gated", "failed"}  # EvalRunDetail.status values that mean the run is finished


def _http(method: str, url: str, headers: dict, body: dict | None, timeout: float) -> tuple[int, dict]:
    """The one network call; tests monkeypatch it. Non-2xx raises urllib.error.HTTPError."""
    req = urllib.request.Request(url, method=method, headers=headers,
                                 data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read() or b"{}")


class Senso:
    def __init__(self):
        self.key = os.environ.get("SENSO_API_KEY")
        if not self.key:
            raise RuntimeError("SENSO_API_KEY is not set")

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float = 30):
        return _http(method, BASE + path, {"X-API-Key": self.key, "Content-Type": "application/json", "User-Agent": "personal-agents/0.1"}, body, timeout)

    def add_document(self, title: str, text: str) -> dict:
        """POST /org/kb/raw -> 202 ContentResponse (id, kb_node_id, processing_status). Searchable once ingestion finishes."""
        return self._call("POST", "/org/kb/raw", {"title": title, "text": text})[1]

    def search(self, query: str, limit: int = 3) -> list[dict]:
        """POST /org/search/context (chunks only, no generated answer). Each result is a SearchResultChunk."""
        return self._call("POST", "/org/search/context",
                          {"query": query, "max_results": limit, "search_type": "hybrid"})[1].get("results", [])

    def check(self, text: str, question: str) -> dict:
        """POST /org/evals/text with wait=true: 200 = finished run, 202 = run handle (still going, status 'pending')."""
        code, run = self._call("POST", "/org/evals/text", {
            "text": text, "question": question[:2000], "author": "organization", "wait": True}, timeout=60)
        done = code == 200 and run.get("status") in _DONE
        return {"id": run.get("eval_run_id"), "status": run["status"] if done else "pending",
                "accuracy_pct": run.get("accuracy_pct"), "band": run.get("band"),
                "claims": [{k: c.get(k) for k in ("claim_text", "source_text", "verdict", "reasoning", "quote", "evidence")}
                           for c in run.get("claims", [])]}
