"""Load the cached products plus a DEMO policy into Senso's knowledge base. Run:
set -a && . ./.env && set +a && uv run python scripts/load_senso.py
Skips ids already recorded in .data/senso_loaded.json. New documents need a moment to finish processing before search finds them."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.senso import Senso  # noqa: E402
from contracts.models import Product  # noqa: E402

RECORD = ROOT / ".data" / "senso_loaded.json"

POLICY = ("DEMO POLICY (fictional, for the hackathon demo only; not a real store's policy).\n\n"
          "Shipping: orders ship from the demo warehouse and arrive in about 3 business days. "
          "Shipping estimate for the demo: $4.99 flat, free over $35.\n\n"
          "Returns: unopened grocery items may be returned within 30 days for a refund to the original payment method. "
          "Opened or perishable items are not returnable.")


def product_doc(p: Product) -> tuple[str, str]:
    ing = f"Ingredients: {', '.join(p.ingredients)}." if p.ingredients else "Ingredient list not published by the store."
    return f"{p.name} ({p.source})", (f"# {p.name}\n\n- Store: {p.source}\n- Price: ${p.price}\n- Pack size: {p.pack_size}\n"
                                      f"- URL: {p.url}\n\n{ing}\n")


if __name__ == "__main__":
    done = set(json.loads(RECORD.read_text())) if RECORD.exists() else set()
    docs = [("demo-policy", "DEMO policy: shipping and returns (fictional)", POLICY)]
    for f in sorted((ROOT / "agent" / "product_cache").glob("*.json")):
        for raw in json.loads(f.read_text()):
            p = Product(**raw)
            docs.append((p.id, *product_doc(p)))
    senso, added = Senso(), 0
    for key, title, text in docs:
        if key in done:
            continue
        senso.add_document(title, text)
        done.add(key)
        RECORD.parent.mkdir(exist_ok=True)
        RECORD.write_text(json.dumps(sorted(done)))  # saved per document so a failed run resumes where it stopped
        added += 1
    print(f"Added {added} documents ({len(done)} loaded in total).")
