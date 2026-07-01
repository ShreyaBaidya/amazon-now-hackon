"""Live SpeakNow validation against real Bedrock.

Runs the app's own hardcoded demo scenarios (the scripted intents + starter
chips) through the real agent and prints the resolved cart with relevance and
safety checks. Use this to eyeball that the LLM returns real, relevant results.

Run from repo root:  uv run --project backend python scripts/validate_speaknow.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import bedrock, data, engine  # noqa: E402

SCENARIOS = [
    "Making carbonara for 6 tonight",
    "A guest is vegan — what can I make?",
    "milk, eggs, bread, coffee, 2 onions",
    "https://www.themealdb.com/meal/lasagne",
    "Got a headache and we're out of coffee",
    "I want to cook biryani",
]


def main():
    ping = bedrock.ping() if _safe_ping() else {"ok": False}
    if not ping.get("ok"):
        print("Bedrock unavailable — cannot run live validation.")
        print("Reason:", _safe_ping_error())
        sys.exit(1)
    print(f"Bedrock OK · {ping['region']} · {ping['model_id']}\n")

    block = data.active_user().get("dietary", {}).get("allergens", [])
    for q in SCENARIOS:
        print("─" * 70)
        print("Q:", q)
        try:
            out = engine._agent_resolve(q)
        except Exception as e:  # noqa: BLE001
            print("  ✗ agent error (would fall back):", e)
            continue
        print("  reply:", out["reply"])
        if out.get("recipe"):
            print("  recipe:", out["recipe"]["name"], f"(serves {out['recipe']['servings']})")
        for p in out["products"]:
            real = bool(data.product(p["id"]))
            safe = not data.allergen_conflict(data.product(p["id"]), block) if real else False
            flag = "✓" if real and safe else "✗"
            print(f"    {flag} {p['name']}  ₹{p['price']}  [{p['id']}]")
        print(f"  total ₹{out['total']} · {len(out['products'])} items")


def _safe_ping():
    try:
        return bedrock.ping().get("ok") is True
    except Exception:
        return False


def _safe_ping_error():
    try:
        bedrock.ping()
        return "ok"
    except Exception as e:  # noqa: BLE001
        return str(e)


if __name__ == "__main__":
    main()
