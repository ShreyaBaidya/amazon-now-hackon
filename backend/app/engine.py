"""Core demo logic: NowCast prediction, recipe scaling, NowSpeak intent, NowSOS."""
from __future__ import annotations

import json
import re

from . import bedrock, gemini, azure, data


# --------------------------------------------------------------------------
# NowCast — fuse fridge + history + calendar into one explainable cart.
# The signals are config; the fusion logic is real (and extensible to live data).
# --------------------------------------------------------------------------

def _fridge_signals() -> list[dict]:
    out = []
    for it in data.fridge()["items"]:
        if it["status"] == "out":
            reason = "You're out" + (f" — {it['note']}" if it.get("note") else "")
        elif it["status"] == "low":
            reason = "Running low" + (f" — {it['note']}" if it.get("note") else "")
        else:
            continue
        out.append({"product_id": it["product_id"], "qty": 1,
                    "reason": reason, "signal": "fridge"})
    return out


def _history_signals() -> list[dict]:
    ratio = data.settings()["reorder_due_ratio"]
    out = []
    for c in data.history()["cadence"]:
        due_at = c["avg_interval_days"] * ratio
        if c["last_ordered_days_ago"] >= due_at:
            out.append({
                "product_id": c["product_id"], "qty": 1,
                "reason": f"Reorder due — every {c['avg_interval_days']} days, "
                          f"last {c['last_ordered_days_ago']} days ago",
                "signal": "history",
            })
    return out


def _hero_event() -> dict | None:
    return next((e for e in data.calendar()["events"] if e.get("is_hero")), None)


def _calendar_signals() -> list[dict]:
    ev = _hero_event()
    if not ev:
        return []
    return [{"product_id": n["product_id"], "qty": n.get("qty", 1),
             "reason": n["reason"], "signal": "calendar"} for n in ev.get("needs", [])]


_SIGNAL_META = {
    "calendar": {"title": "For tonight's dinner party", "icon": "calendar",
                 "blurb": "From your calendar"},
    "fridge": {"title": "Running low at home", "icon": "fridge",
               "blurb": "Your smart fridge"},
    "history": {"title": "Time to reorder", "icon": "repeat",
                "blurb": "From your habits"},
}
_ORDER = ["calendar", "fridge", "history"]


def nowcast() -> dict:
    user = data.active_user()

    groups: dict[str, list] = {k: [] for k in _ORDER}
    total = 0
    count = 0

    for source, sig_fn in [("calendar", _calendar_signals),
                           ("fridge", _fridge_signals),
                           ("history", _history_signals)]:
        for s in sig_fn():
            p = data.product(s["product_id"])
            if not p:
                continue
            item = data.decorate(p, user)
            line = {
                "product": item,
                "qty": s["qty"],
                "reason": s["reason"],
                "reasons": [s["reason"]],
                "signals": [source],
                "line_total": p["price"] * s["qty"],
            }
            groups[source].append(line)
            total += line["line_total"]
            count += s["qty"]

    out_groups = []
    for sig in _ORDER:
        items = groups[sig]
        if not items:
            continue
        items.sort(key=lambda x: -x["line_total"])
        out_groups.append({"signal": sig, **_SIGNAL_META[sig],
                           "subtotal": sum(i["line_total"] for i in items),
                           "items": items})

    ev = _hero_event()
    st = data.settings()
    hour = data.now().hour
    part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    return {
        "greeting": f"Good {part}, {user['first_name']}",
        "headline": "Your cart's ready before you asked",
        "subtext": "Built from your fridge, your habits and your calendar.",
        "event": ev,
        "fridge_sync": data.fridge()["updated_label"],
        "groups": out_groups,
        "item_count": count,
        "total": total,
        "eta_min": st["eta_default_min"],
        "store": st["dark_store"],
    }


# --------------------------------------------------------------------------
# Recipes — real proportional scaling
# --------------------------------------------------------------------------

def _scale_qty(qty, factor):
    if qty is None:
        return None
    v = qty * factor
    return int(v) if abs(v - round(v)) < 1e-6 else round(v, 2)


def recipe_scaled(rid: str, servings: int) -> dict | None:
    r = next((x for x in data.recipes() if x["id"] == rid), None)
    if not r:
        return None
    base = r.get("base_servings", 2) or 2
    factor = servings / base
    user = data.active_user()
    ings = []
    total = 0
    for ing in r["ingredients"]:
        p = data.product(ing["product_id"])
        sq = _scale_qty(ing.get("qty"), factor)
        disp = f"{sq:g} {ing['unit']}".strip() if sq is not None else ing.get("measure", "")
        dec = data.decorate(p, user) if p else None
        price = p["price"] if p else ing.get("price", 0)
        ings.append({
            "product": dec,
            "name": ing["name"],
            "display_qty": disp,
            "base_measure": ing.get("measure", ""),
            "price": price,
        })
        total += price
    return {**{k: r[k] for k in ("id", "name", "cuisine", "category", "image",
                                  "time_min", "dietary_tags", "steps")},
            "base_servings": base, "servings": servings,
            "ingredients": ings, "ingredient_count": len(ings), "total": total}


def recipe_list() -> list[dict]:
    return [{"id": r["id"], "name": r["name"], "cuisine": r["cuisine"],
             "category": r.get("category", ""), "image": r["image"],
             "time_min": r["time_min"], "dietary_tags": r["dietary_tags"],
             "ingredient_count": r["ingredient_count"]} for r in data.recipes()]


# --------------------------------------------------------------------------
# NowSpeak — match scripted intent, else fall back to catalog search
# --------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+")
_STOP = {"the", "and", "for", "with", "recipe", "how", "make", "cook", "want",
         "need", "tonight", "please", "some", "what", "can", "get", "buy",
         "https", "http", "www", "com", "meal", "recipes"}


def _keyword_resolve(query: str) -> dict:
    raw = query or ""
    q = raw.lower().strip()
    sc = data.scenarios()["nowspeak"]

    # 1) a recipe link / URL — "fetch" the dish and pull every ingredient.
    #    (before keyword intents: a URL/list is an explicit structured input.)
    url = _URL_RE.search(raw)
    if url:
        rec = _match_recipe(url.group(0))
        if rec:
            return _recipe_speak(rec, 4, f"Pulled “{rec['name']}” from that link — "
                                 f"here's every ingredient, ready to add.",
                                 f"From your link · serves 4")

    # 2) a pasted list — resolve each item to a product
    if "," in raw or "\n" in raw:
        items = _split_list(raw)
        if len(items) >= 2:
            user = data.active_user()
            prods, seen = [], set()
            for term in items:
                p = _best_match(term)
                if p and p["id"] not in seen:
                    seen.add(p["id"])
                    prods.append(data.decorate(p, user))
            if prods:
                return {
                    "reply": f"Got your list — found {len(prods)} of {len(items)} items. "
                             "Tap add and they're on the way.",
                    "products": prods, "recipe": None,
                    "note": f"{len(prods)} items from your list",
                    "total": sum(p["price"] for p in prods),
                }

    # 3) scripted intents — crisp demo lines (carbonara, vegan guest, etc.)
    for intent in sc["intents"]:
        if any(m in q for m in intent["match"]):
            return _speak_payload(intent)

    # 4) free-form "what to cook" — match a dish by name
    rec = _match_recipe(q)
    if rec:
        return _recipe_speak(rec, 4, f"{rec['name']} it is — I scaled it for 4 and "
                             "pulled the full ingredient list.", "Serves 4 · tap to add")

    # 5) fallback: search the catalog with noun extraction
    nouns = re.findall(r'\b[a-z]+\b', q)
    nouns = [n for n in nouns if len(n) > 2 and n not in {"this", "that", "what", "with", "have",
             "should", "need", "would", "could", "some", "there", "here", "from", "they", "them",
             "been", "very", "just", "about", "than", "then", "also", "over", "your", "help",
             "want", "get", "got", "now", "can"}]
    results = []
    seen = set()
    for n in nouns[:4]:
        for p in data.retrieve(n, limit=3):
            if p["id"] not in seen:
                seen.add(p["id"])
                results.append(p)
    if not results:
        results = data.search(raw, limit=4) or []
    if not results:
        return {"reply": "Sorry, I couldn't find relevant products for that. Try describing what you need in simpler terms.",
                "products": [], "recipe": None, "note": "", "total": 0}
    return {
        "reply": sc["fallback_reply"],
        "products": results, "recipe": None,
        "note": f"{len(results)} matches",
        "total": sum(p["price"] for p in results),
    }


def _speak_payload(intent: dict) -> dict:
    user = data.active_user()
    products = [data.decorate(data.product(pid), user)
                for pid in intent.get("product_ids", []) if data.product(pid)]
    recipe = recipe_scaled(intent["recipe_id"], intent.get("servings", 4)) \
        if intent.get("recipe_id") else None
    return {
        "reply": intent["reply"],
        "products": products,
        "recipe": recipe,
        "dietary_note": intent.get("dietary_note"),
        "note": intent.get("note", ""),
        "total": sum(p["price"] for p in products),
    }


def _recipe_speak(rec: dict, servings: int, reply: str, note: str) -> dict:
    user = data.active_user()
    prods, seen = [], set()
    for ing in rec["ingredients"]:
        p = ing.get("product")
        if p and p["id"] not in seen:
            seen.add(p["id"])
            prods.append(data.decorate(data.product(p["id"]), user))
    return {"reply": reply, "products": prods, "recipe": rec, "note": note,
            "total": sum(p["price"] for p in prods)}


def _split_list(text: str) -> list[str]:
    parts = re.split(r"[,\n;]+|\band\b", text)
    out = []
    for p in parts:
        t = re.sub(r"^\s*\d+\s*(x|pcs|kg|g|ml|l|packs?)?\s*", "", p.strip(), flags=re.I)
        t = t.strip(" .-•*")
        if t:
            out.append(t)
    return out


def _best_match(term: str):
    """Match a single shopping-list item to a product by name/key (not category)."""
    t = term.strip().lower()
    sing = t[:-1] if t.endswith("s") else t
    if len(t) < 2:
        return None
    best, best_key = None, (0, 0.0)
    for p in data.catalog():
        name = p["name"].lower()
        mk = (p.get("match_key") or "").lower()
        words = set(re.split(r"[^a-z]+", name))
        score = 0
        if mk and mk in (t, sing):
            score += 12
        if t in words or sing in words:
            score += 8
        if name.startswith(t):
            score += 4
        elif t in name:
            score += 2
        if mk and (t in mk or sing in mk):
            score += 3
        if score:
            key = (score, p["rating"])
            if key > best_key:
                best, best_key = p, key
    return best


def _find_recipe_id(text: str) -> str | None:
    toks = {t for t in re.split(r"[^a-z]+", text.lower()) if len(t) > 3 and t not in _STOP}
    best, best_score = None, 0
    for r in data.recipes():
        rtoks = {t for t in re.split(r"[^a-z]+", r["name"].lower()) if len(t) > 3 and t not in _STOP}
        score = len(toks & rtoks)
        if score > best_score:
            best, best_score = r, score
    return best["id"] if best else None


def _match_recipe(text: str):
    rid = _find_recipe_id(text)
    return recipe_scaled(rid, 4) if rid else None


# --------------------------------------------------------------------------
# NowSpeak — real agent (Amazon Bedrock). One model, a small tool set, a
# capped tool loop. The model understands the request and PICKS; deterministic
# code does all retrieval and enforces allergens. Any failure (throttle, no
# creds, empty result) falls back to the keyword resolver above — the demo
# never breaks.
# --------------------------------------------------------------------------

_AGENT_SYSTEM = """You are a helpful quick-commerce shopping buddy for Amazon Now in India (prices in ₹). \
The shopper tells you a situation — how they feel, what they're doing, an event they're hosting — and you figure \
out what they need, spanning fresh groceries, home essentials, party supplies, electronics, or lifestyle items, and build the cart.

Shopper: {name}. Allergens to AVOID at all costs: {allergens}. Dietary preference: {diet}.

IMPORTANT — ALWAYS search for products. Never respond with just advice or text.
For ANY request — medical, emotional, household, party — search for relevant products.
If the shopper asks for multiple categories (e.g. food AND cleaning), add ALL categories to cart.

Hard rules:
- You may ONLY add products returned by search_catalog or find_recipe. NEVER invent product ids.
- Never add anything containing the shopper's allergens.
- Search broadly, pick the single best match for each item (prefer higher rating + diet).
- search_catalog: use atomic nouns. GOOD: "pasta", "sauce", "roses", "candle".
  BAD: "italian pasta", "pasta sauce", "red roses", "scented candle".

How to think:
1. Understand the shopper's real-world situation.
2. Infer both explicit and implicit needs.
3. Think like an experienced Amazon shopping assistant helping a customer complete their mission quickly.
4. Consider: guests, occasion, time of day, convenience, serving essentials, comfort.
5. Convert every need to simple atomic nouns. Search. Then add_to_cart.
6. Add ALL item categories the shopper asked for — don't skip any.

Examples:
- "got hurt" -> paracetamol, adhesive bandages, vaporub, antiseptic
- "headache" -> paracetamol, tea, ginger, vaporub
- "cold and fever" -> paracetamol, ORS, soup, ginger, tea, honey, vaporub
- "stomach upset" -> ORS, curd, ginger, lemon, eno, digestive biscuits
- "kitty party" -> samosa, biscuits, drinks, plates, tissues
- "romantic dinner" -> pasta, sauce, flowers, candle, chocolate
- "in-laws visiting" -> tea, snacks, sweets, napkins, handwash, floor cleaner
- "cleaning" -> dishwash, floor cleaner, toilet cleaner, garbage bags
- "party" -> balloons, cups, cake, snacks, drinks
- "road trip" -> wipes, sanitizer, snacks, charger, water
"""
_AGENT_TOOLS = [
    {"toolSpec": {
        "name": "search_catalog",
        "description": "Search the grocery catalog for products. Pass individual product keywords as array items. Example: ['chips', 'water', 'bread']",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array", 
                    "items": {"type": "string"},
                    "description": "Clean, individual product terms. Example: ['samosa', 'biscuits', 'napkins']"
                },
                "category": {"type": "string", "description": "Optional category id to narrow results"},
            },
            "required": ["queries"]}}}},
    {"toolSpec": {
        "name": "find_recipe",
        "description": "Find a real recipe and its ingredient products for a dish or 'what can I cook' request.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "descript¯ion": "Dish or cuisine, e.g. 'carbonara'"},
                "servings": {"type": "integer", "description": "Servings to scale to (default 4)"},
            },
            "required": ["query"]}}}},
    {"toolSpec": {
        "name": "add_to_cart",
        "description": "MANDATORY: Call this to add products to the cart. Without this call, nothing gets added.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"product_id": {"type": "string"},
                                   "qty": {"type": "integer"}},
                    "required": ["product_id", "qty"]}},
            },
            "required": ["items"]}}}},
]


def _agent_handlers(state: dict, block: list[str]):
    def h_search(inp: dict) -> dict:
        raw_qs = inp.get("queries") or []
        qs = []

        for q in raw_qs:
            if isinstance(q, str) and "," in q:
                qs.extend(
                    [x.strip().lower() for x in q.split(",") if x.strip()]
                )
            else:
                qs.append(str(q).strip().lower())

        results = {}

        for q in qs[:10]:

            rows = data.retrieve(
                q,
                inp.get("category", ""),
                limit=5,
                exclude_allergens=block
            )

            filtered = []

            for p in rows:

                name = p["name"].lower()

                if (
                    q in name
                    or any(word == q for word in name.split())
                    or q == p.get("match_key", "").lower()
                ):
                    filtered.append(p)

            if not filtered:
                filtered = rows[:1]

            best = filtered[:1]

            results[q] = best

            state["searched"].extend(best)

            print(
                f"[NowSpeak] search_catalog → '{q}' →",
                [r["name"] for r in best]
            )

        return {"results": results}

    def h_recipe(inp: dict) -> dict:
        rid = _find_recipe_id(inp.get("query", ""))
        print(f"[NowSpeak] find_recipe → '{inp.get('query', '')}' → {'found: '+rid if rid else 'not found'}")
        if not rid:
            return {"found": False}
        servings = int(inp.get("servings") or 4)
        rec = recipe_scaled(rid, max(1, min(12, servings)))
        state["recipe_id"], state["servings"] = rid, servings
        ings = [{"product_id": i["product"]["id"], "name": i["name"],
                 "display_qty": i["display_qty"]}
                for i in rec["ingredients"] if i.get("product")]
        return {"found": True, "name": rec["name"], "servings": servings, "ingredients": ings}

    MAX_CART_ITEMS = 20

    def h_add(inp: dict) -> dict:

        existing = set()

        for p in state["picks"]:
            existing.add(p["product_id"])

        for it in inp.get("items", []):

            if len(state["picks"]) >= MAX_CART_ITEMS:
                break

            pid = it.get("product_id")

            if not data.product(pid):
                continue

            if pid in existing:
                continue

            state["picks"].append({
                "product_id": pid,
                "qty": max(1, int(it.get("qty") or 1)),
            })

            existing.add(pid)

            print(
                f"[NowSpeak] add_to_cart → '{pid}'"
            )

        return {
            "ok": True,
            "added": len(state["picks"])
        }

    return {"search_catalog": h_search, "find_recipe": h_recipe, "add_to_cart": h_add}


_DISH_EXTRACT_PATTERNS = [
    re.compile(r'(?:make|cook|prepare|cooking|making|recipe\s+for)\s+([a-z\s]+?)(?:$|\.|,|and|\s+with|\s+also)'),
    re.compile(r'([a-z\s]+?)\s+recipe'),
]
_FOOD_WORDS = {'biryani', 'pasta', 'curry', 'dal', 'rice', 'roti', 'naan', 'paneer',
    'chicken', 'mutton', 'fish', 'egg', 'salad', 'soup', 'sandwich', 'pizza',
    'noodle', 'dosa', 'idli', 'chapati', 'paratha', 'pulao', 'korma', 'tikka',
    'kebab', 'burger', 'wrap', 'bread', 'cake', 'cookie', 'biscuit', 'dessert',
    'sweet', 'snack', 'chaat', 'samosa', 'pakora', 'pancake', 'waffle', 'brownie',
    'muffin', 'pie', 'quiche', 'frittata', 'curd', 'yogurt', 'rice', 'daal',
    'dal', 'rajma', 'chole', 'chana', 'sabzi', 'subzi', 'sambar', 'rasam'}

def _extract_dish_name(query: str) -> str | None:
    q = query.lower().strip()
    for pat in _DISH_EXTRACT_PATTERNS:
        m = pat.search(q)
        if m:
            dish = m.group(1).strip()
            if dish and len(dish) > 2:
                return dish
    words = set(re.findall(r'[a-z]+', q))
    if words & _FOOD_WORDS:
        return q
    return None

_AI_INGREDIENTS_SYSTEM = """Given a dish name, list the ingredients needed to cook it for 4 people.
Respond ONLY with a valid JSON array of strings — ingredient names. No markdown, no explanation.
Example response: ["chicken", "rice", "yogurt", "onion", "ginger", "garlic", "biryani masala", "oil", "salt"]
Max 15 ingredients. Use simple grocery search terms."""

def _ai_generate_ingredients(dish_name: str) -> list[str]:
    """Generate ingredient list for a dish using Bedrock (primary) or Azure (fallback)."""
    try:
        if bedrock.available():
            msgs = [{"role": "user", "content": [{"text": dish_name}]}]
            resp = bedrock.converse(msgs, system=_AI_INGREDIENTS_SYSTEM)
            raw = resp["output"]["message"]["content"][0]["text"].strip()
        elif azure.available():
            msgs = [{"role": "user", "content": [{"text": dish_name}]}]
            msgs_out, _ = azure.run_tools(msgs, _AI_INGREDIENTS_SYSTEM, [], {}, max_calls=1)
            raw = ""
            for m in reversed(msgs_out):
                if m.get("role") == "assistant":
                    raw = " ".join(b["text"] for b in m.get("content", []) if "text" in b)
                    break
        else:
            return []
        raw = re.sub(r'```(?:json)?', '', raw).strip()
        result = json.loads(raw)
        return [str(x).strip() for x in result if x] if isinstance(result, list) else []
    except Exception:
        return []

def _resolve_recipe_products(query: str, block: list[str]) -> tuple[list[dict], dict | None, str]:
    """Resolve recipe products: deterministic lookup first, then AI fallback.
    Returns (products, recipe_info, reply_text)."""
    user = data.active_user()
    
    # 1) Deterministic recipe match
    recipe_id = _find_recipe_id(query)
    if recipe_id:
        rec = recipe_scaled(recipe_id, 4)
        prods = []
        for ing in rec["ingredients"]:
            p = ing.get("product")
            if p and p["id"]:
                full = data.product(p["id"])
                if full and not data.allergen_conflict(full, block):
                    prods.append(data.decorate(full, user))
        if prods:
            return prods, rec, f"Found {rec['name']} recipe — {len(prods)} ingredients ready"
    
    # 2) AI fallback — generate ingredients
    dish = _extract_dish_name(query)
    if dish:
        ings = _ai_generate_ingredients(dish)
        if ings:
            prods, seen = [], set()
            for name in ings:
                best = _best_match(name)
                if best and best["id"] not in seen and not data.allergen_conflict(best, block):
                    seen.add(best["id"])
                    prods.append(data.decorate(best, user))
            if prods:
                return prods, None, f"Found {len(prods)} ingredients for your request"
    
    return [], None, ""


def _final_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "assistant":
            txt = " ".join(b["text"] for b in m.get("content", []) if "text" in b).strip()
            if txt:
                return txt
    return ""

def _agent_resolve(query: str, recipe_handled: bool = False,
                   recipe_name: str = "") -> dict:
    user = data.active_user()
    diet = user.get("dietary", {})
    block = diet.get("allergens", [])

    state = {
        "picks": [],
        "searched": [],
        "recipe_id": None,
        "servings": 4
    }

    system = _AGENT_SYSTEM.format(
        name=user.get("first_name", "there"),
        allergens=", ".join(block) or "none",
        diet=", ".join(diet.get("preferences", [])) or "no restriction",
    )
    
    if recipe_handled:
        system += (
            f"\n\nIMPORTANT: The recipe for {recipe_name} is ALREADY being handled. "
            "Do NOT search for recipe ingredients. Only search for additional items "
            "the shopper might need — cleaning supplies, party decorations, snacks, "
            "drinks, or other non-recipe extras."
        )

    messages = [{"role": "user", "content": [{"text": query}]}]

    runners = []
    if azure.available():
        runners.append(azure)
    if bedrock.available():
        runners.append(bedrock)
    runners.append(gemini)
    messages, _calls = [], 0
    for runner in runners:
        try:
            print(f"[NowSpeak] Trying {runner.__name__}")

            messages, _calls = runner.run_tools(
                [{"role": "user", "content": [{"text": query}]}],
                system,
                _AGENT_TOOLS,
                _agent_handlers(state, block),
                max_calls=6
            )

            print(f"[NowSpeak] Success using {runner.__name__}")
            break

        except Exception as e:
            print(f"[NowSpeak] {runner.__name__} failed: {e}")

            if state["picks"] or state["recipe_id"]:
                break

            continue

    if not state["picks"] and state["searched"]:
        seen_ids = set()
        for r in state["searched"]:
            if isinstance(r, dict) and r.get("id") and r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                state["picks"].append({"product_id": r["id"], "qty": 1})

    seen, prods = set(), []
    for it in state["picks"]:
        if it["product_id"] in seen:
            continue
        p = data.product(it["product_id"])
        if not p:
            continue
        if data.allergen_conflict(p, block):
            continue
        dec = data.decorate(p, user)
        dec["reason"] = "Added just for you ✨"
        seen.add(it["product_id"])
        prods.append(dec)

    recipe = recipe_scaled(state["recipe_id"], state["servings"]) if state["recipe_id"] else None
    if not prods and not recipe:
        raise RuntimeError("agent produced no grounded cart")

    return {
        "reply": _final_text(messages) or "Here's your cart — tap add for anything you need.",
        "products": prods,
        "recipe": recipe,
        "note": f"{len(prods)} items" if prods else (recipe["name"] if recipe else ""),
        "total": sum(p["price"] for p in prods),
    }


def speak_resolve(query: str) -> dict:
    """NowSpeak entry point: recipe-first, then AI agent, then keyword fallback."""
    user = data.active_user()
    block = user.get("dietary", {}).get("allergens", [])

    # Phase 1: Recipe resolution (deterministic lookup → AI generation fallback)
    recipe_products, recipe_info, recipe_reply = _resolve_recipe_products(query, block)
    recipe_handled = bool(recipe_products)
    recipe_name = recipe_info["name"] if recipe_info else ""

    # Phase 2: AI agent for extras (non-recipe items)
    agent_products = []
    agent_reply = ""
    try:
        agent_result = _agent_resolve(query, recipe_handled=recipe_handled,
                                       recipe_name=recipe_name)
        agent_products = agent_result.get("products", [])
        agent_reply = agent_result.get("reply", "")
    except Exception as e:
        print(f"[NowSpeak] Agent failed (non-fatal): {e}")

    # Phase 3: Merge — deduplicate by product_id, recipe products take priority
    seen_ids = set()
    all_products = []
    for p in recipe_products + agent_products:
        if p["id"] not in seen_ids:
            seen_ids.add(p["id"])
            all_products.append(p)

    if not all_products and not recipe_info:
        # Phase 4: Ultimate fallback
        try:
            return _keyword_resolve(query)
        except Exception:
            return {
                "reply": "Sorry, I couldn't find relevant products for that.",
                "products": [], "recipe": None, "note": "", "total": 0
            }

    reply = recipe_reply or agent_reply or "Here's your cart — tap add for anything you need."
    note = f"{len(all_products)} items"
    if recipe_info:
        note = f"{recipe_info['name']} · {note}"

    return {
        "reply": reply,
        "products": all_products,
        "recipe": recipe_info,
        "note": note,
        "total": sum(p["price"] for p in all_products),
    }


# --------------------------------------------------------------------------
# Coupons — evaluate all against the cart, auto-pick the biggest saving
# --------------------------------------------------------------------------

def _cart_totals(items: list[dict]):
    subtotal, by_cat = 0, {}
    for it in items:
        p = data.product(it["product_id"])
        if not p:
            continue
        line = p["price"] * max(1, int(it.get("qty", 1)))
        subtotal += line
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + line
    return subtotal, by_cat


def _coupon_discount(c: dict, subtotal: int, by_cat: dict, delivery_fee: int) -> float:
    t = c["type"]
    if t == "flat":
        return c["value"]
    if t == "percent":
        return min(subtotal * c["value"] / 100, c.get("max_discount", 1e9))
    if t == "category_percent":
        return min(by_cat.get(c["category"], 0) * c["value"] / 100, c.get("max_discount", 1e9))
    if t == "free_delivery":
        return delivery_fee
    return 0


def evaluate_coupons(items: list[dict], payment: str = "upi") -> dict:
    st = data.settings()
    subtotal, by_cat = _cart_totals(items)
    delivery_fee = 0 if subtotal >= st["free_delivery_above"] else st["delivery_fee"]
    out = []
    for c in data.coupons():
        eligible, reason = True, ""
        if subtotal < c.get("min_order", 0):
            eligible = False
            reason = f"Add ₹{c['min_order'] - subtotal} more to unlock"
        elif c.get("payment") and c["payment"] != payment:
            eligible, reason = False, "Amazon Pay UPI only"
        elif c["type"] == "category_percent" and by_cat.get(c["category"], 0) == 0:
            eligible, reason = False, "No matching items in cart"
        elif c["type"] == "free_delivery" and delivery_fee == 0:
            eligible, reason = False, "Delivery already free"
        disc = round(_coupon_discount(c, subtotal, by_cat, delivery_fee)) if eligible else 0
        out.append({**c, "eligible": eligible, "reason": reason, "discount": disc})
    out.sort(key=lambda x: (-int(x["eligible"]), -x["discount"]))
    best = next((x["code"] for x in out if x["eligible"] and x["discount"] > 0), None)
    return {"subtotal": subtotal, "delivery_fee": delivery_fee, "best_code": best, "coupons": out}


def coupon_for(items: list[dict], code: str, payment: str = "upi") -> dict | None:
    ev = evaluate_coupons(items, payment)
    c = next((x for x in ev["coupons"] if x["code"] == code and x["eligible"] and x["discount"] >= 0), None)
    return c


# --------------------------------------------------------------------------
# Orders
# --------------------------------------------------------------------------

_ORDERS: dict[str, dict] = {}
_SEQ = [1000]


def create_order(items: list[dict], eta_min: int | None = None,
                 coupon_code: str | None = None) -> dict:
    _SEQ[0] += 1
    oid = f"AN{_SEQ[0]}"
    st = data.settings()
    subtotal = 0
    lines = []
    for it in items:
        p = data.product(it["product_id"])
        if not p:
            continue
        qty = max(1, int(it.get("qty", 1)))
        lines.append({"product": p, "qty": qty, "line_total": p["price"] * qty})
        subtotal += p["price"] * qty
    fee = 0 if subtotal >= st["free_delivery_above"] else st["delivery_fee"]
    eta = eta_min or st["eta_default_min"]

    discount, coupon = 0, None
    if coupon_code:
        c = coupon_for(items, coupon_code)
        if c:
            discount = c["discount"]
            coupon = {"code": c["code"], "title": c["title"], "discount": discount}

    order = {
        "order_id": oid,
        "items": lines,
        "item_count": sum(l["qty"] for l in lines),
        "subtotal": subtotal,
        "delivery_fee": fee,
        "discount": discount,
        "coupon": coupon,
        "total": max(0, subtotal + fee - discount),
        "savings": discount,
        "eta_min": eta,
        "address": data.active_user().get("address"),
        "store": st["dark_store"],
        "stages": ["Order placed", "Packing at dark store", "Out for delivery", "Arriving now"],
    }
    _ORDERS[oid] = order
    return order


def get_order(oid: str) -> dict | None:
    return _ORDERS.get(oid)


def order_history() -> list[dict]:
    """Past delivered orders (from purchase history) for the Orders screen + reorder."""
    out = []
    for i, o in enumerate(data.history().get("recent_orders", [])):
        lines = []
        for pid in o["items"]:
            p = data.product(pid)
            if p:
                lines.append({"product": data.decorate(p), "qty": 1})
        out.append({
            "order_id": f"AN{9000 + i}",
            "date": o["date"],
            "status": "Delivered",
            "items": lines,
            "item_count": len(lines),
            "total": o["total"],
        })
    return out
