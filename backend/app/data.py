"""Config loading + catalog helpers. All demo data lives in repo-root /config."""
from __future__ import annotations

import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import os

import boto3
from boto3.dynamodb.conditions import Key

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

# --- DynamoDB Configuration ---
AWS_REGION = os.environ.get("AWS_REGION")
USERS_TABLE_NAME = os.environ.get("USERS_TABLE_NAME")
PRODUCTS_TABLE_NAME = os.environ.get("PRODUCTS_TABLE_NAME")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
users_table = dynamodb.Table(USERS_TABLE_NAME)
products_table = dynamodb.Table(PRODUCTS_TABLE_NAME)

def _load(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def settings() -> dict:
    return _load("settings.json")


@lru_cache(maxsize=1)
def personas() -> dict:
    try:
        # Try to scan/query DynamoDB for personas if possible, but keep local fallback
        response = users_table.scan()
        items = response.get("Items", [])
        if items:
            # Reconstruct the original personas format for compatibility
            local_p = _load("personas.json")
            return {
                "active_user": local_p.get("active_user", "aarav"),
                "users": items
            }
    except Exception as e:
        print(f"[DynamoDB] Failed to load personas, falling back to local file. Error: {e}")
    return _load("personas.json")


@lru_cache(maxsize=1)
def fridge() -> dict:
    return _load("fridge.json")


@lru_cache(maxsize=1)
def history() -> dict:
    return _load("history.json")


@lru_cache(maxsize=1)
def calendar() -> dict:
    return _load("calendar.json")


@lru_cache(maxsize=1)
def scenarios() -> dict:
    return _load("scenarios.json")


@lru_cache(maxsize=1)
def family() -> dict:
    return _load("family.json")


@lru_cache(maxsize=1)
def coupons() -> list[dict]:
    return _load("coupons.json")["coupons"]


@lru_cache(maxsize=1)
def catalog() -> list[dict]:
    try:
        response = products_table.scan()
        items = response.get("Items", [])
        if items:
            # DynamoDB returns decimals which we convert to float/int if needed, 
            # but boto3 resource handles most standard JSON types.
            return items
    except Exception as e:
        print(f"[DynamoDB] Failed to load catalog, falling back to local file. Error: {e}")
    return _load("catalog.json")["products"]


@lru_cache(maxsize=1)
def recipes() -> list[dict]:
    return _load("recipes.json")["recipes"]


@lru_cache(maxsize=1)
def _catalog_index() -> dict[str, dict]:
    return {p["id"]: p for p in catalog()}


def product(pid: str) -> dict | None:
    try:
        response = products_table.get_item(Key={"id": pid})
        item = response.get("Item")
        if item:
            return item
    except Exception as e:
        print(f"[DynamoDB] Failed to load product {pid}, falling back to memory. Error: {e}")
    return _catalog_index().get(pid)


_dietary_override: dict | None = None


def set_dietary(d: dict) -> None:
    """Runtime override for the active user's dietary profile. Saves directly to DynamoDB, falling back to memory."""
    global _dietary_override
    prefs = d.get("preferences", [])
    label = ", ".join(p.capitalize() for p in prefs) if prefs else "No diet restriction"
    updated_dietary = {**d, "preferences_label": label}
    _dietary_override = updated_dietary

    try:
        u = active_user()
        uid = u["id"]
        # Update user profile in DynamoDB table
        users_table.update_item(
            Key={"id": uid},
            UpdateExpression="set dietary = :d",
            ExpressionAttributeValues={":d": updated_dietary}
        )
        print(f"[DynamoDB] Successfully updated dietary preferences for user: {uid}")
    except Exception as e:
        print(f"[DynamoDB] Failed to save dietary preferences to DynamoDB, kept in-memory: {e}")


def active_user() -> dict:
    p = personas()
    uid = p["active_user"]
    try:
        # Fetch fresh state directly from DynamoDB for consistency
        response = users_table.get_item(Key={"id": uid})
        u = response.get("Item")
        if u:
            # Apply in-memory override if not yet synced or as local cache
            if _dietary_override is not None:
                u = {**u, "dietary": {**u.get("dietary", {}), **_dietary_override}}
            return u
    except Exception as e:
        print(f"[DynamoDB] Failed to fetch active user from database, falling back to local file. Error: {e}")

    u = next(x for x in p["users"] if x["id"] == uid)
    if _dietary_override is not None:
        u = {**u, "dietary": {**u.get("dietary", {}), **_dietary_override}}
    return u


def now() -> datetime:
    return datetime.fromisoformat(settings()["demo_now"])


# ---- dietary / allergen flagging ------------------------------------------

def _is_diet_excluded(p: dict, prefs: list[str]) -> bool:
    """Return True if this product should be excluded for the given dietary preferences.

    Hierarchy (strictest first):
    - vegan:       only products tagged 'vegan' are shown
    - vegetarian:  only products tagged 'vegetarian' or 'vegan' are shown
                   (eggetarian and non-veg are BOTH excluded)
    - eggetarian:  products tagged 'vegetarian', 'vegan', or 'eggetarian' are shown
    - gluten-free: products tagged 'gluten-free' are shown; others excluded
    - keto/halal:  products tagged with that preference are shown; others excluded
    """
    if not prefs:
        return False
    tags = set(p.get("dietary_tags", []))
    cat = p.get("category", "")

    # Food categories where dietary exclusions apply
    food_cats = {"fresh_produce", "dairy_eggs", "bakery", "staples_grocery",
                 "meat_seafood", "beverages", "snacks", "frozen"}
    is_food = cat in food_cats

    if "vegan" in prefs:
        # Only vegan products allowed
        return is_food and "vegan" not in tags

    if "vegetarian" in prefs:
        # Only vegetarian or vegan products allowed — eggetarian is NOT allowed
        if cat == "meat_seafood":
            return True
        if is_food and tags and "vegetarian" not in tags and "vegan" not in tags:
            return True
        # Products with empty tags in food categories are non-veg by default
        if is_food and not tags and cat in ("snacks", "frozen", "bakery"):
            return True
        return False

    if "eggetarian" in prefs:
        # Vegetarian, vegan, and eggetarian allowed — only pure non-veg excluded
        if cat == "meat_seafood":
            return True
        if is_food and tags and not (tags & {"vegetarian", "vegan", "eggetarian"}):
            return True
        return False

    if "gluten-free" in prefs:
        return is_food and tags and "gluten-free" not in tags

    if "keto" in prefs:
        return is_food and tags and "keto" not in tags

    if "halal" in prefs:
        return cat == "meat_seafood" and "halal" not in tags

    return False


def decorate(p: dict, user: dict | None = None) -> dict:
    """Return a copy of product p with dietary warnings and flags for the given user."""
    if p is None:
        return None
    user = user or active_user()
    diet = user.get("dietary", {})
    out = dict(p)
    warnings: list[str] = []
    prefs = diet.get("preferences", [])
    allergens = set(diet.get("allergens", []))

    # Allergen conflict
    hit = allergens & set(p.get("allergen_tags", []))
    if hit:
        warnings.append("Contains " + ", ".join(sorted(hit)))

    # Dietary preference mismatch warnings
    tags = set(p.get("dietary_tags", []))
    if "vegetarian" in prefs and p.get("category") == "meat_seafood":
        warnings.append("Not vegetarian")
    if "vegan" in prefs and "vegan" not in tags:
        warnings.append("Not vegan")

    out["warnings"] = warnings
    out["allergen_conflict"] = bool(hit)
    # Mark dietary exclusion so the frontend can show/hide appropriately
    out["diet_excluded"] = _is_diet_excluded(p, prefs)
    return out

import re

def search(q: str = "", category: str = "", limit: int = 40,
           show_excluded: bool = False) -> list[dict]:
    """Search the catalog.

    By default, products excluded by the user's dietary preferences are hidden.
    Pass show_excluded=True to include them (with diet_excluded=True flag set).
    """
    q = (q or "").strip().lower()
    cat = (category or "").strip()

    user = active_user()
    prefs = user.get("dietary", {}).get("preferences", [])

    rows = catalog()

    if cat:
        rows = [p for p in rows if p["category"] == cat]

    if not q:
        return rows[:limit]

    q_words = set(re.findall(r"[a-z]+", q))

    scored = []

    for p in rows:
        name = p["name"].lower()
        brand = p["brand"].lower()
        category_name = p["category"].lower()
        match_key = (p.get("match_key") or "").lower()

        name_words = set(re.findall(r"[a-z]+", name))
        brand_words = set(re.findall(r"[a-z]+", brand))
        category_words = set(re.findall(r"[a-z]+", category_name))
        match_words = set(re.findall(r"[a-z]+", match_key))

        score = 0

        # exact product name
        if q == name:
            score += 200

        # exact keyword match
        if q in name_words:
            score += 150

        if q in match_words:
            score += 120

        if q in brand_words:
            score += 50

        if q in category_words:
            score += 30

        # token overlap
        overlap = len(
            q_words &
            (name_words | brand_words | category_words | match_words)
        )

        score += overlap * 20

        # weak substring fallback
        if score == 0:
            if name.startswith(q):
                score += 15

            elif q in name:
                score += 5

        if score >= 20:
            scored.append((score, p))

        scored.sort(
            key=lambda x: (-x[0], -x[1]["rating"])
        )

        rows = [p for _, p in scored]
    else:
        rows = sorted(rows, key=lambda p: -p["rating"])

    # decorated = [decorate(p, user) for p in rows[:limit * 2]]  # extra headroom for filtering
    #
    # if not show_excluded and prefs:
    #     decorated = [p for p in decorated if not p.get("diet_excluded")]
    # return decorated[:limit]

    decorated = [decorate(p, user) for p in rows[:limit * 2]]
    return decorated[:limit]

    print(
        f"[SEARCH DEBUG] {q}:",
        [(s, p["name"]) for s, p in scored[:5]]
    )

    return rows[:limit]

# Indian-grocery synonyms: map what users type -> extra terms to also match.
_SYNONYMS = {
    "curd": ["yogurt", "dahi"], "yogurt": ["curd", "dahi"],
    "capsicum": ["bell pepper"], "bell pepper": ["capsicum"],
    "brinjal": ["eggplant", "aubergine"], "eggplant": ["brinjal"],
    "lady finger": ["okra", "bhindi"], "okra": ["bhindi", "lady finger"],
    "coriander": ["cilantro", "dhania"], "cilantro": ["coriander"],
    "atta": ["flour", "wheat"], "maida": ["flour"],
    "paneer": ["cottage cheese"], "jeera": ["cumin"],
    "chillies": ["chilli", "chili"], "spring onion": ["scallion"],
     "biscuits": ["cookies"],
    "cookies": ["biscuits"],

    "cold drink": ["coke", "pepsi", "soft drink", "soda"],

    "samosa": ["snack", "frozen snack"],

    "flowers": ["roses", "bouquet"],

    "candle": ["scented candle"],

    "tea": ["chai"],

    "handwash": ["liquid handwash", "hand wash", "soap"],
    "hand wash": ["handwash", "liquid handwash", "soap"],

    "napkin": ["napkins", "tissue", "paper napkin", "paper napkins"],
    "napkins": ["tissue", "paper napkins", "napkin"],
    "plate": ["plates", "paper plate", "paper plates", "disposable plate", "disposable plates"],
    "plates": ["paper plates", "disposable plates", "plate"],
        # Tablecloth / party supplies
    "tablecloth": ["table cover", "plastic table cover"],
    "table cloth": ["table cover", "plastic table cover"],
    
    # Rice precision — stops "rice" matching "rice stick noodles"
    # by giving it a strong preferred match
    "rice": ["basmati rice", "basmati"],
    "basmati": ["basmati rice", "rice"],
    
    # More party supply gaps
    "forks": ["disposable forks", "plastic forks"],
    "plates": ["paper plates", "disposable plates"],
    "candles": ["birthday candles", "candle"],
}


def _expand(term: str) -> list[str]:
    t = term.strip().lower()
    return [t, *_SYNONYMS.get(t, [])]


    # Allergen keyword backstop — catalog allergen_tags are incomplete (many nut
    # products are untagged), so safety can't depend on tags alone. Names are
    # specific to avoid false positives ("coconut"/"nutmeg"/"chestnut" are NOT nuts).

# Category fallback — when a search term matches a high-level intent (e.g.
# "cleaning", "hurt", "party"), return the top-rated products from that
# category instead of nothing.
_CATEGORY_FALLBACK = {
    "household_cleaning": ["clean", "cleaning", "household"],
    "medicine_health": ["medicine", "first aid", "pain", "hurt", "injury",
                        "sick", "ill", "wound", "tablet", "bandage"],
    "party_festive": ["party", "birthday", "celebration", "festive", "decoration"],
    "snacks": ["snack", "snacks", "munchies"],
    "beverages": ["drink", "drinks", "beverage"],
    "fresh_produce": ["vegetable", "vegetables", "fruit", "fruits", "produce"],
    "personal_care": ["handwash", "soap", "shampoo", "sanitizer", "deodorant"],
}
_ALLERGEN_KEYWORDS = {
    "nuts": ["cashew", "cashews", "almond", "almonds", "peanut", "peanuts",
             "walnut", "walnuts", "pista", "pistachio", "pistachios",
             "hazelnut", "pecan", "pine nut", "pine-nut", "macadamia", "praline",
             "nuts", "cashewnut", "cashewnuts", "almondmilk"],
    "dairy": ["milk", "cheese", "butter", "paneer", "ghee", "cream", "yogurt", "curd"],
    "gluten": ["wheat", "atta", "maida", "bread", "pasta", "noodle", "barley"],
    "soy": ["soy", "tofu", "edamame"],
    "shellfish": ["prawn", "shrimp", "crab", "lobster"],
    "eggs": ["egg"],
}


def allergen_conflict(p: dict, block) -> bool:
    """True if product p conflicts with any allergen in `block` — via tag OR name."""
    block = set(block or [])
    if not block:
        return False
    if block & set(p.get("allergen_tags", [])):
        return True
    # Fix: Split name into full word boundaries to avoid false positives (e.g. 'wheat' vs 'buckwheat')
    name_words = set(re.split(r"[^a-z]+", p["name"].lower()))
    for a in block:
        keywords = _ALLERGEN_KEYWORDS.get(a, [])
        if any(k in name_words for k in keywords):
            return True
    return False

def _score(p: dict, terms: list[str]) -> int:
    name = p["name"].lower()
    words = set(re.split(r"[^a-z]+", name))
    mk = (p.get("match_key") or "").lower()
    hay = f"{name} {p['brand']} {p['category']}".lower()
    score = 0
    for term in terms:
        sing = term[:-1] if term.endswith("s") else term
        if mk and mk in (term, sing):
            score += 12
        if term in words or sing in words:
            score += 8
        if name.startswith(term):
            score += 4
        elif term in hay:
            score += 2
        if mk and (term in mk or sing in mk):
            score += 3
    return score


def compact(p: dict) -> dict:
    """Token-lean product view for the LLM tool result (no description/image)."""
    return {"id": p["id"], "name": p["name"], "brand": p["brand"],
            "price": p["price"], "size": p.get("size", ""),
            "category": p["category"], "rating": p["rating"],
            "dietary_tags": p.get("dietary_tags", []),
            "allergen_tags": p.get("allergen_tags", [])}


# def retrieve(query: str, category: str = "", limit: int = 8,
#              exclude_allergens: list[str] | None = None) -> list[dict]:
#     """Deterministic ranked search for one query. Allergen-conflict items are
#     dropped before results are returned, so the agent never sees them."""
#     terms = _expand(query)
#     cat = (category or "").strip()
#     block = exclude_allergens or []
#     scored = []
#     for p in catalog():
#         if cat and p["category"] != cat:
#             continue
#         if allergen_conflict(p, block):
#             continue
#         s = _score(p, terms)
#         if s:
#             scored.append((s, p))
#     scored.sort(key=lambda x: (-x[0], -x[1]["rating"], -x[1].get("rating_count", 0)))
#     return [compact(p) for _, p in scored[:limit]]

def retrieve(query: str, category: str = "", limit: int = 8,
             exclude_allergens: list[str] | None = None,
             exclude_dietary: list[str] | None = None) -> list[dict]:
    """Deterministic ranked search for one query with fallback substring matching.
    
    - Allergen-conflict items are dropped (safety gate — never shown to agent)
    - Diet-excluded items are also dropped so the agent only picks from
      products compatible with the user's dietary preferences
    """

    terms = _expand(query)
    cat = (category or "").strip()
    block = exclude_allergens or []
    prefs = exclude_dietary or []
    scored = []
    
    # Pre-clean the query string for substring fallback matching
    q_clean = query.lower().strip()
    
    for p in catalog():
        if cat and p["category"] != cat:
            continue
        if allergen_conflict(p, block):
            continue
        if prefs and _is_diet_excluded(p, prefs):
            continue
        if prefs and _is_diet_excluded(p, prefs):
            continue     
        s = _score(p, terms)
        
        # --- SMART FALLBACK ---
        # If the official scoring returns 0, manually check if the query is hidden 
        # inside the match_key, product name, or description.
        if not s and q_clean:
            match_key = str(p.get("match_key", "")).lower()
            p_name = str(p.get("name", "")).lower()
            p_desc = str(p.get("description", "")).lower()
            
            if q_clean in match_key or q_clean in p_name or q_clean in p_desc:
                s = 1  # Give it a base structural score so it gets included
                
        if s:
            scored.append((s, p))
            
    # --- CATEGORY FALLBACK ---
    # If nothing scored, check if the query is a high-level intent keyword
    # and return top products from that category.
    if not scored:
        for cat, keywords in _CATEGORY_FALLBACK.items():
            if any(kw in q_clean for kw in keywords):
                cat_prods = [p for p in catalog() if p["category"] == cat]
                cat_prods.sort(key=lambda p: (-p.get("rating", 0), -p.get("rating_count", 0)))
                scored = [(50, p) for p in cat_prods[:limit]]
                print(f"[CATEGORY FALLBACK] '{q_clean}' → {cat} ({len(scored)} products)")
                break

    scored.sort(key=lambda x: (-x[0], -x[1]["rating"], -x[1].get("rating_count", 0)))
    return [compact(p) for _, p in scored[:limit]]


CATEGORIES = [
    ("fresh_produce", "Fresh", "🥬"),
    ("dairy_eggs", "Dairy & Eggs", "🥚"),
    ("bakery", "Bakery", "🍞"),
    ("staples_grocery", "Staples", "🌾"),
    ("meat_seafood", "Meat & Fish", "🍗"),
    ("beverages", "Beverages", "🥤"),
    ("snacks", "Snacks", "🍫"),
    ("frozen", "Frozen", "🧊"),
    ("medicine_health", "Pharmacy", "💊"),
    ("personal_care", "Personal Care", "🧴"),
    ("household_cleaning", "Household", "🧽"),
    ("baby_care", "Baby", "🍼"),
    ("home_decor_lifestyle", "Lifestyle & Flowers", "🌸"),
    ("party_festive", "Party Supplies", "🎉"),
]
