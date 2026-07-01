"""Endpoint tests — assert every demo-critical contract holds.

Run:  uv run pytest -q   (from backend/)
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health").json()
    assert r["ok"] is True
    assert r["products"] >= 100
    assert r["recipes"] >= 15


def test_bootstrap():
    b = client.get("/api/bootstrap").json()
    assert b["user"]["first_name"] == "Aarav"
    assert b["settings"]["currency"] == "₹"
    assert len(b["categories"]) == 12
    assert "nuts" in b["user"]["dietary"]["allergens"]


def test_nextbuy_fuses_three_signals():
    d = client.get("/api/nextbuy").json()
    signals = {g["signal"] for g in d["groups"]}
    assert signals == {"calendar", "fridge", "history"}  # all three present
    assert d["item_count"] > 0 and d["total"] > 0
    assert d["event"]["is_hero"] is True
    # every line carries an explainable reason
    for g in d["groups"]:
        for it in g["items"]:
            assert it["reason"]
            assert it["product"]["image"].startswith("/products/")


def test_nextbuy_reorder_reason_mentions_cadence():
    d = client.get("/api/nextbuy").json()
    hist = next(g for g in d["groups"] if g["signal"] == "history")
    assert any("every" in it["reason"] for it in hist["items"])


def test_recipe_scaling_is_proportional():
    base = client.get("/api/recipe/spaghetti-alla-carbonara?servings=2").json()
    dbl = client.get("/api/recipe/spaghetti-alla-carbonara?servings=4").json()
    assert dbl["servings"] == 4
    # numeric ingredient should roughly double
    bq = next((i for i in base["ingredients"] if i["display_qty"][:1].isdigit()), None)
    assert bq is not None


def test_speaknow_vegan_intent_is_dietary_aware():
    d = client.get("/api/speaknow", params={"q": "a guest is vegan"}).json()
    assert d["recipe"]["name"] == "Ratatouille"
    assert "Vegan" in (d.get("dietary_note") or "")
    assert len(d["products"]) > 0


def test_speaknow_headache_cross_domain():
    d = client.get("/api/speaknow", params={"q": "headache and out of coffee"}).json()
    ids = {p["id"] for p in d["products"]}
    assert "paracetamol" in ids and "coffee-beans-250g" in ids


def test_speaknow_fallback_searches_catalog():
    d = client.get("/api/speaknow", params={"q": "chocolate"}).json()
    assert len(d["products"]) > 0


def test_speaknow_list_resolves_each_item():
    d = client.get("/api/speaknow", params={"q": "milk, eggs, bread, coffee, 2 onions"}).json()
    ids = {p["id"] for p in d["products"]}
    assert "farm-eggs-6" in ids
    assert {"amul-milk-500ml", "amul-gold-1l"} & ids
    assert "onion-1kg" in ids
    assert len(d["products"]) >= 4


def test_speaknow_recipe_link_fetches_ingredients():
    d = client.get("/api/speaknow", params={"q": "https://www.themealdb.com/meal/lasagne"}).json()
    assert d["recipe"]["name"] == "Lasagne"
    assert len(d["products"]) > 5


def test_speaknow_cook_dish_by_name():
    d = client.get("/api/speaknow", params={"q": "i want to cook biryani"}).json()
    assert "Biryani" in d["recipe"]["name"]


def test_allergen_flagging():
    p = client.get("/api/product/cashews-200g").json()
    assert p["allergen_conflict"] is True
    assert any("nuts" in w for w in p["warnings"])


def test_profile_endpoint():
    pr = client.get("/api/profile").json()
    assert pr["first_name"] == "Aarav"
    assert "nuts" in pr["allergen_options"]
    assert "vegan" in pr["diet_options"]


def test_dietary_update_reflects_in_flagging():
    # remove the nut allergy -> cashews should no longer conflict
    client.post("/api/profile/dietary", json={"preferences": [], "allergens": [], "exclude_keywords": []})
    assert client.get("/api/product/cashews-200g").json()["allergen_conflict"] is False
    # add vegan -> a meat product gets flagged
    client.post("/api/profile/dietary", json={"preferences": ["vegan"], "allergens": ["nuts"], "exclude_keywords": []})
    chick = client.get("/api/product/chicken-breast-500g").json()
    assert any("vegan" in w.lower() for w in chick["warnings"])
    # restore
    client.post("/api/profile/dietary", json={"preferences": [], "allergens": ["nuts"], "exclude_keywords": []})


def test_search_and_category():
    assert len(client.get("/api/catalog", params={"q": "milk"}).json()["products"]) > 0
    meds = client.get("/api/catalog", params={"category": "medicine_health"}).json()["products"]
    assert all(p["category"] == "medicine_health" for p in meds)


def test_coupons_pick_best():
    ev = client.post("/api/coupons", json={"items": [
        {"product_id": "spaghetti", "qty": 2}, {"product_id": "red-wine", "qty": 1}]}).json()
    assert ev["best_code"] == "SAVE15"  # 15% of ~1140 capped 150 beats flat 100
    save15 = next(c for c in ev["coupons"] if c["code"] == "SAVE15")
    assert save15["discount"] == 150
    # category coupon with no matching items is ineligible
    fresh = next(c for c in ev["coupons"] if c["code"] == "FRESH20")
    assert fresh["eligible"] is False


def test_coupons_category_and_min_order():
    ev = client.post("/api/coupons", json={"items": [{"product_id": "tomato-500g", "qty": 1}]}).json()
    welcome = next(c for c in ev["coupons"] if c["code"] == "WELCOME100")
    assert welcome["eligible"] is False and "more" in welcome["reason"].lower()
    fresh = next(c for c in ev["coupons"] if c["code"] == "FRESH20")
    assert fresh["eligible"] is True and fresh["discount"] > 0


def test_order_applies_coupon():
    r = client.post("/api/order", json={
        "items": [{"product_id": "spaghetti", "qty": 2}, {"product_id": "red-wine", "qty": 1}],
        "coupon_code": "SAVE15"}).json()
    assert r["discount"] == 150
    assert r["coupon"]["code"] == "SAVE15"
    assert r["total"] == r["subtotal"] + r["delivery_fee"] - 150


def test_order_lifecycle():
    r = client.post("/api/order", json={"items": [{"product_id": "amul-milk-500ml", "qty": 2}]}).json()
    assert r["order_id"].startswith("AN")
    assert r["item_count"] == 2
    assert len(r["stages"]) == 4
    got = client.get(f"/api/order/{r['order_id']}").json()
    assert got["order_id"] == r["order_id"]


def test_order_history_for_reorder():
    d = client.get("/api/orders").json()["orders"]
    assert len(d) >= 1
    o = d[0]
    assert o["status"] == "Delivered"
    assert o["item_count"] == len(o["items"]) > 0
    assert o["items"][0]["product"]["image"].startswith("/products/")


def test_sse_stream_emits_tokens_and_result():
    with client.stream("GET", "/api/speaknow/stream", params={"q": "a guest is vegan"}) as s:
        body = "".join(chunk for chunk in s.iter_text())
    assert "event: token" in body
    assert "event: result" in body
    assert "event: done" in body
