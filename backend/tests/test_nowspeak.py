"""SpeakNow agent tests.

Two layers:
  * Mocked — drive the tool loop / assembly with a fake Bedrock, no network.
    Assert the guarantees that make the agent "real": grounding (no
    hallucinated products), allergen safety, and graceful fallback.
  * Live — run the app's own hardcoded demo scenarios against real Bedrock
    and assert relevant, grounded carts. Skipped when Bedrock is unavailable
    (no creds / daily throttle).

Run:  uv run pytest -q
"""
import pytest

from app import bedrock, data, engine


# --------------------------------------------------------------------------
# Deterministic retrieval (no model involved)
# --------------------------------------------------------------------------

def test_retrieve_is_grounded_and_relevant():
    milk = data.retrieve("milk", exclude_allergens=["nuts"])
    assert milk and milk[0]["category"] == "dairy_eggs"
    assert all(data.product(p["id"]) for p in milk)  # every id is real


def test_synonyms_match_indian_terms():
    names = " ".join(p["name"].lower() for p in data.retrieve("curd"))
    assert "curd" in names or "yogurt" in names or "dahi" in names


@pytest.mark.parametrize("term", ["cashew", "peanut", "walnut", "pine nut", "almond"])
def test_allergen_backstop_blocks_every_nut(term):
    assert data.retrieve(term, exclude_allergens=["nuts"]) == []


@pytest.mark.parametrize("term", ["coconut", "nutmeg", "chestnut mushroom"])
def test_allergen_backstop_keeps_false_positives(term):
    assert data.retrieve(term, exclude_allergens=["nuts"])  # not actually nuts


# --------------------------------------------------------------------------
# Agent assembly + safety (fake the model via run_tools)
# --------------------------------------------------------------------------

def _fake_run_tools(picks, reply="Done.", recipe_query=None):
    def run(messages, system, tools, handlers, max_calls=10):
        handlers["search_catalog"]({"queries": ["milk", "eggs"]})
        if recipe_query:
            handlers["find_recipe"]({"query": recipe_query, "servings": 4})
        handlers["add_to_cart"]({"items": picks})
        messages.append({"role": "assistant", "content": [{"text": reply}]})
        return messages, 2
    return run


def test_agent_drops_hallucinated_ids(monkeypatch):
    monkeypatch.setattr(bedrock, "run_tools",
                        _fake_run_tools([{"product_id": "amul-milk-500ml", "qty": 1},
                                         {"product_id": "totally-made-up-id", "qty": 1}]))
    out = engine.speak_resolve("get me milk")
    ids = {p["id"] for p in out["products"]}
    assert "amul-milk-500ml" in ids
    assert "totally-made-up-id" not in ids  # invented id rejected
    assert all(data.product(i) for i in ids)


def test_agent_safety_gate_drops_allergen(monkeypatch):
    # model wrongly picks an (untagged) nut product; gate must drop it for Aarav
    monkeypatch.setattr(bedrock, "run_tools",
                        _fake_run_tools([{"product_id": "amul-milk-500ml", "qty": 1},
                                         {"product_id": "cashews", "qty": 1}]))
    out = engine.speak_resolve("milk and cashews")
    ids = {p["id"] for p in out["products"]}
    assert "amul-milk-500ml" in ids
    assert "cashews" not in ids


def test_agent_reply_is_passed_through(monkeypatch):
    monkeypatch.setattr(bedrock, "run_tools",
                        _fake_run_tools([{"product_id": "amul-milk-500ml", "qty": 1}],
                                        reply="Got your milk, Aarav!"))
    assert engine.speak_resolve("milk")["reply"] == "Got your milk, Aarav!"


def test_agent_falls_back_to_keyword_on_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bedrock down")
    monkeypatch.setattr(bedrock, "run_tools", boom)
    out = engine.speak_resolve("milk, eggs, bread")  # keyword list path
    assert out["products"]  # fallback still returns a usable cart


def test_agent_empty_cart_falls_back(monkeypatch):
    monkeypatch.setattr(bedrock, "run_tools", _fake_run_tools([]))  # model picks nothing
    out = engine.speak_resolve("milk")
    assert out["products"]  # degraded to keyword resolver, not an empty cart


# --------------------------------------------------------------------------
# run_tools loop (fake converse)
# --------------------------------------------------------------------------

def test_run_tools_loop_runs_handlers_then_stops(monkeypatch):
    turns = [
        {"stopReason": "tool_use", "output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "t1", "name": "search_catalog", "input": {"queries": ["milk"]}}}]}}},
        {"stopReason": "end_turn", "output": {"message": {"role": "assistant", "content": [
            {"text": "All set."}]}}},
    ]
    seen = []
    monkeypatch.setattr(bedrock, "converse", lambda *a, **k: turns.pop(0))
    msgs, calls = bedrock.run_tools(
        [{"role": "user", "content": [{"text": "milk"}]}],
        "sys", [], {"search_catalog": lambda inp: seen.append(inp) or {"ok": True}})
    assert calls == 1 and seen == [{"queries": ["milk"]}]
    assert engine._final_text(msgs) == "All set."


def test_run_tools_respects_max_calls(monkeypatch):
    # model that never stops asking for tools — loop must cap
    monkeypatch.setattr(bedrock, "converse", lambda *a, **k: {
        "stopReason": "tool_use", "output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "t", "name": "search_catalog", "input": {"queries": ["x"]}}}]}}})
    _msgs, calls = bedrock.run_tools(
        [{"role": "user", "content": [{"text": "x"}]}], "sys", [],
        {"search_catalog": lambda inp: {"ok": True}}, max_calls=3)
    assert calls == 3  # bounded, no runaway


# --------------------------------------------------------------------------
# Live — the app's hardcoded demo scenarios, resolved by REAL Bedrock
# --------------------------------------------------------------------------

def _bedrock_live() -> bool:
    try:
        return bedrock.ping().get("ok") is True
    except Exception:
        return False


live = pytest.mark.skipif(not _bedrock_live(),
                          reason="Bedrock unavailable (no creds or daily throttle)")


@live
@pytest.mark.parametrize("query", [
    "Making carbonara for 6 tonight",
    "A guest is vegan — what can I make?",
    "milk, eggs, bread, coffee, 2 onions",
    "Got a headache and we're out of coffee",
    "I want to cook biryani",
])
def test_live_scenarios_return_grounded_safe_carts(query):
    out = engine._agent_resolve(query)  # force agent path (no fallback)
    assert out["products"] or out["recipe"], f"empty cart for: {query}"
    for p in out["products"]:
        assert data.product(p["id"]), "hallucinated product id"
        assert not data.allergen_conflict(data.product(p["id"]), ["nuts"]), \
            f"allergen leak: {p['name']}"
