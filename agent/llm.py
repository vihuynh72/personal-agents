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
        return json.dumps({"kind": "home_dinner", "when": "Saturday", "headcount": 6})

    def system2(self, prompt: str) -> str:
        if "TASK: forbidden" in prompt:
            restriction = re.search(r"restriction: (.+)", prompt).group(1).strip().lower()
            return json.dumps(_FORBIDDEN.get(restriction, []))
        return json.dumps(["spaghetti", "marinara sauce", "salad", "sparkling water", "garlic bread"])


class RealLLM:
    """Unverified end to end (no keys at build time). SDKs are imported lazily so tests need neither."""

    def __init__(self):
        import anthropic
        from google import genai

        self._claude = anthropic.Anthropic()
        self._claude_model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
        self._gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self._gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

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
