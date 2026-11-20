"""Agent-to-agent protocol (node N27): each person's agent guards their profile; the host's agent negotiates a menu."""
import json
import uuid
from pathlib import Path

from .llm import LLM
from .profiles import _SAFE, ProfileStore
from .workflow import _ask, _matches

SCOPES = {"dietary", "availability"}


def _safe(pid: str) -> str:
    if not _SAFE.fullmatch(pid or ""):  # ids arrive over HTTP; never let them form a path or key
        raise ValueError(f"unsafe id: {pid!r}")
    return pid


class Connections:
    """Directed consent edges on disk: owner lets `to`'s agent ask for owner's data within the scopes."""

    def __init__(self, data_dir: str = ".data"):
        self.path = Path(data_dir) / "connections.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _all(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def _write(self, d: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d))
        tmp.replace(self.path)

    def grant(self, owner_id: str, to_id: str, scopes) -> set:
        if bad := set(scopes) - SCOPES:
            raise ValueError(f"unknown scopes: {sorted(bad)}")
        d, key = self._all(), f"{_safe(owner_id)}>{_safe(to_id)}"
        d[key] = sorted(set(d.get(key, [])) | set(scopes))
        self._write(d)
        return set(d[key])

    def revoke(self, owner_id: str, to_id: str) -> None:
        d = self._all()
        d.pop(f"{_safe(owner_id)}>{_safe(to_id)}", None)
        self._write(d)

    def scopes(self, owner_id: str, to_id: str) -> set:
        return set(self._all().get(f"{_safe(owner_id)}>{_safe(to_id)}", []))


def _msg(type_: str, from_: str, to: str, body: dict) -> dict:
    return {"type": type_, "from": from_, "to": to, "id": uuid.uuid4().hex[:8], "body": body}


def _dishes(menu) -> list[dict]:
    """Normalize a model's menu: name, lowercase ingredients, main flag, cuisine."""
    return [{"name": str(d["name"]), "ingredients": [str(i).lower() for i in d.get("ingredients") or []],
             "main": bool(d.get("main")), "cuisine": str(d.get("cuisine") or "")}
            for d in menu if isinstance(d, dict) and d.get("name")]


class PersonAgent:
    def __init__(self, person_id: str, store: ProfileStore, connections: Connections, tools=None, llm: LLM | None = None,
                 transcript: list | None = None, min_dishes: int = 2):
        self.id, self.store, self.conn, self.tools, self.llm = _safe(person_id), store, connections, tools, llm
        self.transcript = [] if transcript is None else transcript
        self.min_dishes = min_dishes

    def _avoid(self) -> tuple[list[str], bool]:
        """Hard constraints as plain ingredients; restriction names are expanded so the reason never leaves."""
        p = self.store.get(self.id)
        if p is None:
            raise KeyError(self.id)
        out, complete = [a.lower() for a in p.allergens], True
        for r in p.restrictions:
            if r.lower().startswith("no "):
                out.append(r[3:].lower())
                continue
            f, ok = _ask(self.llm.system2,
                "TASK: forbidden. List the ingredients a person with this dietary restriction cannot eat. "
                "Reply with a JSON array of lowercase ingredient names only.\n"
                f"restriction: {r}", []) if self.llm else ([], False)
            out += [str(x).lower() for x in f]
            complete &= ok  # a failed expansion makes every dish unsafe below, never silently safe
        return list(dict.fromkeys(out)), complete

    def handle(self, message: dict) -> dict:
        self.transcript.append(message)
        reply = self._reply(message)
        self.transcript.append(reply)
        return reply

    def _reply(self, m: dict) -> dict:
        sender, body, kind = _safe(m.get("from", "")), m.get("body") or {}, m.get("type")
        need = {"constraints.request": "dietary", "availability.request": "availability", "proposal": "dietary"}
        if kind not in need:
            return _msg("refused", self.id, sender, {"reason": "unknown type", "re": m.get("id")})
        if need[kind] not in self.conn.scopes(self.id, sender):
            return _msg("refused", self.id, sender, {"reason": "no consent", "re": m.get("id")})
        if kind == "constraints.request":
            avoid, _ = self._avoid()
            return _msg("constraints.reply", self.id, sender, {"constraints": [{"avoid": a, "hard": True} for a in avoid]})
        if kind == "availability.request":
            cands = list(body.get("candidate_times") or [])
            free = getattr(self.tools, "free_times", None)
            if free:
                return _msg("availability.reply", self.id, sender, {"times": free(self.id, cands), "comment": "checked calendar"})
            return _msg("availability.reply", self.id, sender,
                        {"times": cands, "comment": "no calendar connected; all candidate times treated as free"})
        avoid, complete = self._avoid()
        menu = _dishes(body.get("menu") or [])
        ok = [d for d in menu if complete and not any(_matches(a, x) for a in avoid for x in [d["name"], *d["ingredients"]])]
        names = [d["name"] for d in ok]
        if len(ok) >= self.min_dishes and any(d["main"] for d in ok):
            return _msg("accept", self.id, sender, {"ok_dishes": names})
        what = "a main" if not any(d["main"] for d in ok) else f"{self.min_dishes} dishes"
        return _msg("counter", self.id, sender, {"need": f"{what} without {', '.join(avoid) or 'unverified ingredients'}",
                                                 "ok_dishes": names})


def _menu_prompt(request: str, avoid: list[str], needs: list[str]) -> str:
    return ("TASK: a2a_menu. Plan a shared menu of 4 to 6 dishes for this gathering. Vary the cuisines. "
            "Every listed ingredient to avoid is a hard rule for at least one guest: include at least one main that "
            "avoids all of them, and enough sides that each guest has two or more dishes. "
            "Reply with a JSON array only: [{\"name\", \"ingredients\": [lowercase], \"main\": true|false, \"cuisine\"}].\n"
            f"Request: {request}\nAvoid: {json.dumps(avoid)}\nNeeds: {json.dumps(needs)}")


def plan_gathering(host_id: str, guest_ids: list[str], request: str, candidate_times: list[str], store: ProfileStore,
                   connections: Connections, tools, llm: LLM, max_rounds: int = 3) -> dict:
    transcript: list = []
    host = PersonAgent(host_id, store, connections, tools, llm, transcript)
    agents = {g: PersonAgent(g, store, connections, tools, llm, transcript) for g in guest_ids}
    out = {"status": None, "time": None, "menu": [], "per_guest": {}, "rounds": 0, "no_consent": [], "transcript": transcript}

    avoid, times = host._avoid()[0], set(candidate_times)
    for g, a in list(agents.items()):
        c = a.handle(_msg("constraints.request", host_id, g, {}))
        t = a.handle(_msg("availability.request", host_id, g, {"candidate_times": candidate_times}))
        if "refused" in (c["type"], t["type"]):
            out["no_consent"].append(g)  # excluded, never guessed at
            del agents[g]
            continue
        avoid += [x["avoid"] for x in c["body"]["constraints"]]
        times &= set(t["body"]["times"])
    avoid = list(dict.fromkeys(avoid))
    if not times:
        return {**out, "status": "no_common_time"}
    out["time"] = min(times)  # ISO strings sort chronologically

    needs: list[str] = []
    for r in range(1, max_rounds + 1):
        out["rounds"] = r
        menu, _ = _ask(llm.system2, _menu_prompt(request, avoid, needs), [])
        out["menu"] = _dishes(menu)
        replies = {g: a.handle(_msg("proposal", host_id, g, {"menu": out["menu"], "time": out["time"]}))
                   for g, a in agents.items()}
        out["per_guest"] = {g: {"can_eat": rep["body"].get("ok_dishes", [])} for g, rep in replies.items()}
        counters = [rep["body"]["need"] for rep in replies.values() if rep["type"] == "counter"]
        if not counters:
            return {**out, "status": "agreed"}
        needs = list(dict.fromkeys(needs + counters))
    return {**out, "status": "needs_host", "unresolved": counters}  # the only case a human is asked


def shopping_request(plan: dict) -> str:
    n = len(plan["per_guest"]) + 1  # guests plus the host
    return f"ingredients for: {', '.join(d['name'] for d in plan['menu'])} for {n} people"
