"""Core demo logic: NowCast prediction, recipe scaling, NowSpeak intent, NowSOS."""
from __future__ import annotations

import re

from . import data, gcal


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


def _live_calendar() -> dict:
    """Return calendar data — live Google Calendar when connected, else mock."""
    return gcal.get_calendar_with_fallback()


def _hero_event() -> dict | None:
    """Pick the hero event from today's calendar data only.

    For live Google Calendar data, hero selection is done in gcal.select_hero.
    For mock data, fall back to the legacy is_hero flag — but only if that
    event is actually today.
    """
    cal = _live_calendar()
    events = cal.get("events", [])
    # events list is already filtered to today by get_calendar_with_fallback
    return next((e for e in events if e.get("is_hero")), None)


def _calendar_signals() -> list[dict]:
    """Build NowCast signals from the hero event's needs list.

    Works with both live (AI-inferred) and static needs[] arrays.
    """
    ev = _hero_event()
    if not ev:
        return []
    return [
        {
            "product_id": n["product_id"],
            "qty": n.get("qty", 1),
            "reason": n["reason"],
            "signal": "calendar",
        }
        for n in ev.get("needs", [])
    ]


_SIGNAL_META = {
    "calendar": {"title": "For your upcoming event", "icon": "calendar",
                 "blurb": "From your calendar"},
    "fridge": {"title": "Running low at home", "icon": "fridge",
               "blurb": "Your smart fridge"},
    "history": {"title": "Time to reorder", "icon": "repeat",
                "blurb": "From your habits"},
}
_ORDER = ["calendar", "fridge", "history"]


def nowcast() -> dict:
    user = data.active_user()
    raw = _calendar_signals() + _fridge_signals() + _history_signals()

    # merge by product, keep the highest-priority signal but collect all reasons
    merged: dict[str, dict] = {}
    for s in raw:
        pid = s["product_id"]
        if pid not in merged:
            merged[pid] = {**s, "reasons": [s["reason"]], "signals": [s["signal"]]}
        else:
            m = merged[pid]
            m["qty"] = max(m["qty"], s["qty"])
            if s["reason"] not in m["reasons"]:
                m["reasons"].append(s["reason"])
            if s["signal"] not in m["signals"]:
                m["signals"].append(s["signal"])
            # promote to highest-priority signal for grouping
            if _ORDER.index(s["signal"]) < _ORDER.index(m["signal"]):
                m["signal"] = s["signal"]

    groups: dict[str, list] = {k: [] for k in _ORDER}
    total = 0
    count = 0
    for m in merged.values():
        p = data.product(m["product_id"])
        if not p:
            continue
        item = data.decorate(p, user)
        line = {
            "product": item,
            "qty": m["qty"],
            "reason": m["reasons"][0],
            "reasons": m["reasons"],
            "signals": m["signals"],
            "line_total": p["price"] * m["qty"],
        }
        groups[m["signal"]].append(line)
        total += line["line_total"]
        count += m["qty"]

    out_groups = []
    ev = _hero_event()

    # Build a dynamic title for the calendar group based on the hero event
    cal_title = "For your upcoming event"
    if ev:
        t = ev.get("title", "")
        if t:
            # Strip emoji and trim for a clean card title
            clean = re.sub(r"[^\w\s\-&'@]", "", t).strip()
            cal_title = f"For: {clean}" if clean else "For your upcoming event"

    for sig in _ORDER:
        items = groups[sig]
        if not items:
            continue
        items.sort(key=lambda x: -x["line_total"])
        meta = dict(_SIGNAL_META[sig])
        if sig == "calendar":
            meta["title"] = cal_title
        out_groups.append({"signal": sig, **meta,
                           "subtotal": sum(i["line_total"] for i in items),
                           "items": items})

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


def _is_recipe_excluded(r: dict, prefs: list[str]) -> bool:
    """Return True if this recipe conflicts with the user's dietary preferences.

    Hierarchy:
    - vegan:       only 'vegan' recipes shown
    - vegetarian:  only 'vegetarian' or 'vegan' — eggetarian is excluded
    - eggetarian:  'vegetarian', 'vegan', 'eggetarian' shown — non-veg excluded
    - gluten-free: only 'gluten-free' recipes shown
    """
    if not prefs:
        return False
    tags = set(r.get("dietary_tags", []))

    if "vegan" in prefs:
        return "vegan" not in tags

    if "vegetarian" in prefs:
        # Strictly only vegetarian or vegan — eggetarian recipes excluded
        return not (tags & {"vegetarian", "vegan"})

    if "eggetarian" in prefs:
        return not (tags & {"vegetarian", "vegan", "eggetarian"})

    if "gluten-free" in prefs:
        return "gluten-free" not in tags

    return False


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


def recipe_list(show_excluded: bool = False) -> list[dict]:
    """Return the recipe list, filtered by the active user's dietary preferences.

    Set show_excluded=True to return all recipes regardless of preferences
    (with diet_excluded flag set so the frontend can still indicate them).
    """
    user = data.active_user()
    prefs = user.get("dietary", {}).get("preferences", [])

    result = []
    for r in data.recipes():
        excluded = _is_recipe_excluded(r, prefs)
        if excluded and not show_excluded:
            continue
        result.append({
            "id": r["id"],
            "name": r["name"],
            "cuisine": r["cuisine"],
            "category": r.get("category", ""),
            "image": r["image"],
            "time_min": r["time_min"],
            "dietary_tags": r["dietary_tags"],
            "ingredient_count": r["ingredient_count"],
            "diet_excluded": excluded,
        })
    return result


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
    user = data.active_user()  # for dietary filtering

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
            prods, seen = [], set()
            for term in items:
                p = _best_match(term)
                if p and p["id"] not in seen:
                    dec = data.decorate(p, user)
                    if dec.get("diet_excluded"):  # skip diet-excluded
                        continue
                    seen.add(p["id"])
                    prods.append(dec)
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

    # 5) fallback: search the catalog
    results = data.search(raw, limit=6)
    return {
        "reply": sc["fallback_reply"],
        "products": results, "recipe": None,
        "note": f"{len(results)} matches",
        "total": sum(p["price"] for p in results),
    }


def _speak_payload(intent: dict) -> dict:
    user = data.active_user()
    products = []
    for pid in intent.get("product_ids", []):
        p = data.product(pid)
        if not p:
            continue
        dec = data.decorate(p, user)
        if dec.get("diet_excluded"):  # skip diet-excluded
            continue
        products.append(dec)
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
            raw_p = data.product(p["id"])
            if not raw_p:
                continue
            dec = data.decorate(raw_p, user)
            if dec.get("diet_excluded"):  # skip diet-excluded ingredients
                continue
            seen.add(p["id"])
            prods.append(dec)
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

_AGENT_SYSTEM = """You are NowSpeak, the shopping agent for Amazon Now, a quick-commerce \
grocery app in India (prices in ₹). You turn a shopper's request into a ready cart of REAL \
products from our catalog.

Shopper: {name}. Allergens to AVOID at all costs: {allergens}. Dietary preference: {diet}.

Hard rules:
- You may ONLY add products that were returned by the search_catalog or find_recipe tools. \
NEVER invent a product name or id.
- Never add anything containing the shopper's allergens.
- Keep it tight: search for the items, pick the single best match for each (prefer higher \
rating and the shopper's diet), then finalise.

How to work:
1. Break the request into concrete product terms.
2. Call search_catalog with those terms (batch several in one call via the `queries` list).
3. For "what can I cook" / dish or recipe requests, call find_recipe and add its ingredients.
4. Call add_to_cart ONCE with your final picks (ids from the tool results only).
5. Then write ONE short, warm sentence to the shopper about what you added. No lists, no markdown."""

_AGENT_TOOLS = [
    {"toolSpec": {
        "name": "search_catalog",
        "description": "Search the real grocery catalog. Pass concrete product terms.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "queries": {"type": "array", "items": {"type": "string"},
                            "description": "Product terms to search, e.g. ['milk','spaghetti','eggs']"},
                "category": {"type": "string", "description": "Optional category id to narrow results"},
            },
            "required": ["queries"]}}}},
    {"toolSpec": {
        "name": "find_recipe",
        "description": "Find a real recipe and its ingredient products for a dish or 'what can I cook' request.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Dish or cuisine, e.g. 'carbonara'"},
                "servings": {"type": "integer", "description": "Servings to scale to (default 4)"},
            },
            "required": ["query"]}}}},
    {"toolSpec": {
        "name": "add_to_cart",
        "description": "Finalise the cart with the chosen products.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"product_id": {"type": "string"},
                                   "qty": {"type": "integer"}},
                    "required": ["product_id"]}},
            },
            "required": ["items"]}}}},
]


def _agent_handlers(state: dict, block: list[str]):
    def h_search(inp: dict) -> dict:
        qs = inp.get("queries") or ([inp["query"]] if inp.get("query") else [])
        cat = inp.get("category", "")
        results = {}
        prefs = user.get("dietary", {}).get("preferences", [])
        for q in [str(x) for x in qs][:8]:
            rows = data.retrieve(q, cat, limit=8, exclude_allergens=block,
                                 exclude_dietary=prefs)
            results[q] = rows
            state["searched"].extend(rows)
        return {"results": results}

    def h_recipe(inp: dict) -> dict:
        rid = _find_recipe_id(inp.get("query", ""))
        if not rid:
            return {"found": False}
        servings = int(inp.get("servings") or 4)
        rec = recipe_scaled(rid, max(1, min(12, servings)))
        state["recipe_id"], state["servings"] = rid, servings
        ings = [{"product_id": i["product"]["id"], "name": i["name"],
                 "display_qty": i["display_qty"]}
                for i in rec["ingredients"] if i.get("product")]
        return {"found": True, "name": rec["name"], "servings": servings, "ingredients": ings}

    def h_add(inp: dict) -> dict:
        for it in inp.get("items", []):
            pid = it.get("product_id")
            if data.product(pid):  # validate against real catalog — drop hallucinated ids
                state["picks"].append({"product_id": pid,
                                       "qty": max(1, int(it.get("qty") or 1))})
        return {"ok": True, "added": len(state["picks"])}

    return {"search_catalog": h_search, "find_recipe": h_recipe, "add_to_cart": h_add}


def _final_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "assistant":
            txt = " ".join(b["text"] for b in m.get("content", []) if "text" in b).strip()
            if txt:
                return txt
    return ""


def _agent_resolve(query: str) -> dict:
    from . import bedrock  # local import: keep keyword path import-light
    user = data.active_user()
    diet = user.get("dietary", {})
    block = diet.get("allergens", [])
    system = _AGENT_SYSTEM.format(
        name=user.get("first_name", "there"),
        allergens=", ".join(block) or "none",
        diet=", ".join(diet.get("preferences", [])) or "no restriction",
    )
    state = {"picks": [], "searched": [], "recipe_id": None, "servings": 4}
    messages = [{"role": "user", "content": [{"text": query}]}]
    messages, _calls = bedrock.run_tools(messages, system, _AGENT_TOOLS,
                                         _agent_handlers(state, block), max_calls=10)

    seen, prods = set(), []
    for it in state["picks"]:
        if it["product_id"] in seen:
            continue
        p = data.product(it["product_id"])
        if not p:
            continue
        if data.allergen_conflict(p, block):  # safety gate — never deliver an allergen
            continue
        dec = data.decorate(p, user)
        if dec.get("diet_excluded"):  # safety gate — never deliver diet-excluded
            continue
        seen.add(it["product_id"])
        prods.append(dec)

    recipe = recipe_scaled(state["recipe_id"], state["servings"]) if state["recipe_id"] else None
    if not prods and not recipe:
        raise RuntimeError("agent produced no grounded cart")  # -> keyword fallback

    return {
        "reply": _final_text(messages) or "Here's your cart — tap add for anything you need.",
        "products": prods,
        "recipe": recipe,
        "note": f"{len(prods)} items" if prods else (recipe["name"] if recipe else ""),
        "total": sum(p["price"] for p in prods),
    }


def speak_resolve(query: str) -> dict:
    """NowSpeak entry point: real Bedrock agent, keyword resolver as fallback."""
    try:
        return _agent_resolve(query)
    except Exception:  # noqa: BLE001 — any agent failure degrades gracefully
        return _keyword_resolve(query)


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
