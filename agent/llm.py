"""Two-speed LLM: system1 (fast, Gemini) for parsing and routing, system2 (deliberate, Claude) for planning."""
import json
import os
import re
from typing import Protocol


class LLM(Protocol):
    def system1(self, prompt: str) -> str: ...

    def system2(self, prompt: str) -> str: ...


_FORBIDDEN = {
    "vegetarian": ["beef", "chicken", "pork", "fish", "bacon", "ham", "lamb", "gelatin", "anchovy", "shrimp"],
    "vegan": ["beef", "chicken", "pork", "fish", "bacon", "ham", "lamb", "gelatin", "anchovy", "shrimp",
              "egg", "milk", "butter", "cheese", "parmesan", "cream", "honey"],
    "halal": ["pork", "bacon", "ham", "gelatin", "wine"],
}


class FakeLLM:
    """Deterministic stand-in; answers the prompts agent/workflow.py sends, keyed on their task tag."""

    def system1(self, prompt: str) -> str:
        if "TASK: profile" in prompt or "TASK: intent" in prompt:
            raw = re.search(r"Message: (.+)", prompt, re.S).group(1).strip()
            msg = raw.lower()
            if "TASK: intent" in prompt:
                intent = ("paid" if re.search(r"\bpaid\b", msg) else
                          "order" if re.search(r"\b(dinner|lunch|breakfast)\b", msg) else
                          "question" if "?" in msg else
                          "change" if re.search(r"\b(instead|cheaper|wanted|rather|make it)\b", msg) else
                          "update" if re.search(r"\b(prefer|actually|instead|allergic|no longer|stop buying)\b", msg) else
                          "order" if re.search(r"\b(get|buy|order|need|want)\b", msg) else "other")
                return json.dumps({"intent": intent})
            name = re.search(r"\b(?:I am|I'm|my name is)\s+([A-Z][a-z]+)", raw)
            prefs = [w for w in re.findall(r"\b(?:prefer|like|love|buy)\s+([a-z][\w'-]*)", msg) if w not in ("it", "to", "a")]
            prefs += [f"under ${n}" for n in re.findall(r"\bunder \$?(\d+)", msg)]
            return json.dumps({
                "name": name.group(1) if name else None,
                "allergens": [a for a in ("peanut", "egg", "milk", "soy", "sesame", "shellfish") if re.search(rf"\b{a}s?\b", msg)],
                "restrictions": [r for r in _FORBIDDEN if re.search(rf"\b{r}\b", msg)],
                "preferences": prefs,
                "request": (m.group(0).strip(" .!") if (m := re.search(r"\b(?:get|buy|order|need|want)\b.*", raw, re.I))
                            else None)})
        m = re.search(r"Request: (.+)", prompt)
        req = m.group(1).lower() if m else ""
        mode = "dinner" if re.search(r"dinner|party|lunch|brunch|night|guests", req) else "self"
        return json.dumps({"mode": mode, "kind": "home_dinner", "when": "Saturday", "headcount": 6})

    def system2(self, prompt: str) -> str:
        if "TASK: shopping" in prompt:
            req = re.search(r"Request: (.+)", prompt).group(1).lower()
            if fix := re.search(r"^(.*?)\.? correction: (.+)$", req):  # chat "change": re-plan the original, then apply it
                base = json.loads(self.system2(f"TASK: shopping\nRequest: {fix.group(1)}"))
                return json.dumps([f"organic {x}" if "organic" in fix.group(2) else x for x in base])
            if re.search(r"\b(dinner|lunch|meal)\b", req):
                return json.dumps(["spaghetti", "marinara sauce", "salad"])
            req = re.sub(r"\b(get me|order|buy|some|please|for myself|for me|i need|i want)\b", " ", req)
            items = [x.strip(" .!") for x in re.split(r",| and ", req) if x.strip(" .!")]
            return json.dumps(["ground coffee" if x == "coffee" else x for x in items])
        if "TASK: answer" in prompt:
            return re.search(r"Facts: (.+)", prompt).group(1)
        if "TASK: forbidden" in prompt:
            restriction = re.search(r"restriction: (.+)", prompt).group(1).strip().lower()
            return json.dumps(_FORBIDDEN.get(restriction, []))
        return json.dumps(["spaghetti", "marinara sauce", "salad", "sparkling water", "garlic bread"])


class RealLLM:
    """Unverified end to end (no keys at build time). SDKs are imported lazily so tests need neither."""

    def __init__(self):
        import anthropic
        from google import genai

        from google.genai import types

        self._claude = anthropic.Anthropic(timeout=120, max_retries=1)  # bounded: no request hangs a run
        self._claude_model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
        self._gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(timeout=60_000))
        self._gemini_model = os.environ.get("GEMINI_MODEL", "gemini-4-neon")

    def system1(self, prompt: str) -> str:
        return self._gemini.models.generate_content(model=self._gemini_model, contents=prompt).text

    def system2(self, prompt: str) -> str:
        r = self._claude.beta.messages.create(
            model=self._claude_model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # re-run on a fallback model if the safety classifier declines
            messages=[{"role": "user", "content": prompt}],
        )
        if r.stop_reason == "refusal":
            raise RuntimeError(f"Claude declined: {r.stop_details}")
        return "".join(b.text for b in r.content if b.type == "text")


def get_llm() -> LLM:
    if os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("GEMINI_API_KEY"):
        return RealLLM()
    return FakeLLM()
