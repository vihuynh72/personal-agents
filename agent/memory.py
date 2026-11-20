"""Memory (node N21): facts about a person from things they already have (Day 0), and a bounded conflict loop.

Every fact is kept in an append-only JSONL log per person; a contradiction marks the loser superseded, never deleted.
"""
import json
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from agent.profiles import _SAFE, ProfileStore
from agent.workflow import _ask
from contracts.models import GuestProfile

KINDS = ("allergen", "restriction", "preference", "dislike", "name")
DIRECT = ("chat", "feedback")  # the person's own words to the agent; everything else is inferred
MAX_ITERATIONS = 5
SAFETY_KEPT = "safety: kept the restriction, needs the person's confirmation"

PROMPT = (
    "TASK: memory. Extract facts about what this person eats, avoids, buys or prefers. Extract ONLY what the text "
    "states; never guess. From a receipt or order, extract only shopping styles and brands (organic, a brand "
    "name), not each item bought. A gift or a purchase for someone else is not a fact about this person. Reply with a JSON "
    'array of {"kind", "value", "polarity", "evidence"} where kind is one of allergen, restriction, preference, '
    'dislike, name; value is a short lowercase singular ingredient, dish, brand or style (e.g. "peanut", '
    '"organic", "folgers"); polarity is "+" when it holds and "-" when the text says it no longer holds; evidence is '
    'the sentence it came from. Examples: "I loved the mushroom risotto" -> preference mushroom; "can\'t stand '
    'cilantro" -> dislike cilantro; "allergic to peanuts" -> allergen peanut "+"; "I can eat peanuts now, the allergy '
    'was a misdiagnosis" -> allergen peanut "-"; "I\'m Rowan" -> name rowan. Reply [] if there is nothing.\n'
)


def _ts(when) -> datetime:
    d = when if isinstance(when, datetime) else datetime.fromisoformat(str(when))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _family(f) -> str:
    return "taste" if f["kind"] in ("preference", "dislike") else f["kind"]


def _stance(f) -> bool:  # True: likes / has it; a "-" dislike means they like it again
    return (f["polarity"] == "+") != (f["kind"] == "dislike")


class Memory:
    def __init__(self, store: ProfileStore, llm, data_dir: str = ".data"):
        self.store, self.llm = store, llm
        self.dir = Path(data_dir) / "memory"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._guard = threading.Lock()
        self.last_iterations = 0

    def _path(self, person_id: str) -> Path:
        if not _SAFE.fullmatch(person_id or ""):  # ids arrive over HTTP; never let them form a path
            raise ValueError(f"unsafe person id: {person_id!r}")
        return self.dir / f"{person_id}.jsonl"

    def _lock(self, person_id: str) -> threading.Lock:
        with self._guard:
            return self._locks[person_id]

    def history(self, person_id: str) -> list[dict]:
        p = self._path(person_id)
        return [json.loads(line) for line in p.read_text().splitlines() if line] if p.exists() else []

    def _write(self, person_id: str, facts: list[dict]) -> None:
        p = self._path(person_id)
        tmp = p.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(f) + "\n" for f in facts))
        tmp.replace(p)

    def add(self, person_id: str, text: str, source: str, when: datetime | None = None) -> dict:
        return self.add_many(person_id, [{"text": text, "source": source, "when": when}])

    def add_many(self, person_id: str, items: list[dict]) -> dict:
        self._path(person_id)  # reject an unsafe id before any model call
        new = [f for it in items for f in self._extract(person_id, it)]
        with self._lock(person_id):
            facts = self.history(person_id) + new
            conflicts = self._resolve(facts)
            self._write(person_id, facts)
            profile = self._rebuild(person_id, [f for f in facts if f["status"] == "active"])
            self.store.save(profile)
            if self.store.get(person_id) != profile:
                raise RuntimeError(f"profile {person_id} did not save as rebuilt")
        return {"profile": profile, "added": new, "conflicts": conflicts}

    def _extract(self, person_id: str, item: dict) -> list[dict]:
        text, source = item.get("text"), str(item.get("source") or "import")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("each item needs a text")
        when = _ts(item.get("when") or datetime.now(timezone.utc)).isoformat()
        out, _ = _ask(self.llm.system1, PROMPT + f"Source: {source}\nText: {text}", [])
        facts = []
        for x in out:
            if not (isinstance(x, dict) and x.get("kind") in KINDS and x.get("polarity") in ("+", "-")
                    and isinstance(x.get("value"), str) and x["value"].strip()):
                continue  # a malformed fact is dropped, never guessed at
            facts.append({"id": uuid.uuid4().hex[:12], "person_id": person_id, "kind": x["kind"],
                          "value": x["value"].strip().lower(), "polarity": x["polarity"], "source": source,
                          "when": when, "evidence": str(x.get("evidence") or text)[:200],
                          "status": "active", "superseded_by": None})
        return facts

    def _resolve(self, facts: list[dict]) -> list[dict]:
        """Read active facts, find contradictions, supersede the losers; repeat on the new memory until clean."""
        order = {f["id"]: i for i, f in enumerate(facts)}
        key = lambda f: (_ts(f["when"]), order[f["id"]])  # noqa: E731  newest last; ties go to the later entry
        conflicts = []
        for self.last_iterations in range(1, MAX_ITERATIONS + 1):
            active = sorted((f for f in facts if f["status"] == "active"), key=key)
            losers = []  # (loser, winner, rule, needs_confirmation); rule None: a duplicate, not a conflict
            groups = defaultdict(list)
            for f in active:
                groups[(_family(f), "" if f["kind"] == "name" else f["value"])].append(f)
            for (fam, _), fs in groups.items():
                win = fs[0]
                for new in fs[1:]:
                    if fam != "name" and _stance(win) == _stance(new):
                        losers.append((win, new, None, False))
                        win = new
                    elif fam in ("allergen", "restriction") and not _stance(new) and new["source"] not in DIRECT:
                        losers.append((new, win, SAFETY_KEPT, True))  # an inferred "-" never lifts a restriction
                    else:
                        losers.append((win, new, "newer statement wins", False))
                        win = new
            lost = {id(x[0]) for x in losers}
            allergens = [f for f in active if f["kind"] == "allergen" and _stance(f) and id(f) not in lost]
            for f in active:
                if _family(f) == "taste" and _stance(f) and id(f) not in lost:
                    if a := next((a for a in allergens if a["value"] in f["value"].split()
                                  or a["value"] + "s" in f["value"].split()), None):
                        losers.append((f, a, "safety: allergen overrides preference", False))
            if not losers:
                break
            for loser, winner, rule, confirm in losers:
                loser["status"], loser["superseded_by"] = "superseded", winner["id"]
                if rule:
                    conflicts.append({"value": loser["value"], "kept": winner, "superseded": loser, "rule": rule,
                                      "needs_confirmation": confirm})
        return conflicts

    def _rebuild(self, person_id: str, active: list[dict]) -> GuestProfile:
        p = self.store.get(person_id) or GuestProfile(id=person_id, name=person_id)
        touched = {f["value"] for f in self.history(person_id) if _family(f) == "taste"}
        # Taste values belong to memory, so drop them and re-add the active ones; allergens and restrictions from
        # elsewhere (onboarding, the form) stay unless the person's own direct "-" statement is active.
        allergens, name = list(p.allergens), p.name
        restrictions = [r for r in p.restrictions if not (r.startswith("no ") and r[3:] in touched)]
        prefs = [x for x in p.preferences if x not in touched]
        for f in sorted(active, key=lambda f: _ts(f["when"])):
            v, has = f["value"], _stance(f)
            target = {"allergen": allergens, "restriction": restrictions}.get(f["kind"])
            if f["kind"] == "name":
                name = v.title()
            elif target is not None:
                if has and v not in target:
                    target.append(v)
                elif not has and f["source"] in DIRECT and v in target:
                    target.remove(v)
            elif has and v not in prefs:
                prefs.append(v)
            elif not has and f"no {v}" not in restrictions:
                restrictions.append(f"no {v}")  # workflow expands each restriction into forbidden ingredients
        return p.model_copy(update={"name": name, "allergens": allergens, "restrictions": restrictions,
                                    "preferences": prefs})
