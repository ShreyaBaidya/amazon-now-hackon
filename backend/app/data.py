"""Config loading + catalog helpers. All demo data lives in repo-root /config."""
from __future__ import annotations

import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _load(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def settings() -> dict:
    return _load("settings.json")


@lru_cache(maxsize=1)
def personas() -> dict:
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
    return _load("catalog.json")["products"]


@lru_cache(maxsize=1)
def recipes() -> list[dict]:
    return _load("recipes.json")["recipes"]


@lru_cache(maxsize=1)
def _catalog_index() -> dict[str, dict]:
    return {p["id"]: p for p in catalog()}


def product(pid: str) -> dict | None:
    return _catalog_index().get(pid)


_dietary_override: dict | None = None


def set_dietary(d: dict) -> None:
    """Runtime override for the active user's dietary profile (from the Profile screen)."""
    global _dietary_override
    prefs = d.get("preferences", [])
    label = ", ".join(p.capitalize() for p in prefs) if prefs else "No diet restriction"
    _dietary_override = {**d, "preferences_label": label}


def active_user() -> dict:
    p = personas()
    uid = p["active_user"]
    u = next(x for x in p["users"] if x["id"] == uid)
    if _dietary_override is not None:
        u = {**u, "dietary": {**u.get("dietary", {}), **_dietary_override}}
    return u


def now() -> datetime:
    return datetime.fromisoformat(settings()["demo_now"])


# ---- dietary / allergen flagging ------------------------------------------

def decorate(p: dict, user: dict | None = None) -> dict:
    """Return a copy of product p with dietary warnings for the given user."""
    if p is None:
        return None
    user = user or active_user()
    diet = user.get("dietary", {})
    out = dict(p)
    warnings: list[str] = []
    allergens = set(diet.get("allergens", []))
    hit = allergens & set(p.get("allergen_tags", []))
    if hit:
        warnings.append("Contains " + ", ".join(sorted(hit)))
    prefs = diet.get("preferences", [])
    if "vegetarian" in prefs and "vegetarian" not in p.get("dietary_tags", []) \
            and p.get("category") == "meat_seafood":
        warnings.append("Not vegetarian")
    if "vegan" in prefs and "vegan" not in p.get("dietary_tags", []):
        warnings.append("Not vegan")
    out["warnings"] = warnings
    out["allergen_conflict"] = bool(hit)
    return out

import re

def search(q: str = "", category: str = "", limit: int = 40) -> list[dict]:
    q = (q or "").strip().lower()
    cat = (category or "").strip()

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
    "nuts": ["cashew", "almond", "peanut", "walnut", "pista", "pistachio",
             "hazelnut", "pecan", "pine nut", "pine-nut", "macadamia", "praline"],
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
             exclude_allergens: list[str] | None = None) -> list[dict]:
    """Deterministic ranked search for one query with fallback substring matching."""
    terms = _expand(query)
    cat = (category or "").strip()
    block = exclude_allergens or []
    scored = []
    
    # Pre-clean the query string for substring fallback matching
    q_clean = query.lower().strip()
    
    for p in catalog():
        if cat and p["category"] != cat:
            continue
        if allergen_conflict(p, block):
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
