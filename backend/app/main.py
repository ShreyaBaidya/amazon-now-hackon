"""Amazon Now demo API — config-driven, deterministic, no external LLM at runtime."""
from __future__ import annotations

import asyncio
import json
import re


from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import azure, bedrock, data, engine, group

app = FastAPI(title="Amazon Now API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True, "products": len(data.catalog()), "recipes": len(data.recipes())}


@app.get("/api/bedrock/ping")
def bedrock_ping(q: str = "Reply with just the word OK."):
    """Connectivity probe for the Bedrock LLM. Surfaces errors verbatim."""
    try:
        return bedrock.ping(q)
    except Exception as e:  # noqa: BLE001 — probe must report any failure
        return {"ok": False, "region": bedrock.REGION,
                "model_id": bedrock.MODEL_ID, "error": str(e)}


@app.get("/api/bootstrap")
def bootstrap():
    """Everything the shell needs on load: settings, active user, categories."""
    u = data.active_user()
    return {
        "settings": data.settings(),
        "user": {
            "id": u["id"], "name": u["name"], "first_name": u["first_name"],
            "avatar_color": u["avatar_color"], "address": u.get("address"),
            "payment": u.get("payment"), "dietary": u.get("dietary"),
        },
        "categories": [{"id": c, "label": l, "emoji": e} for c, l, e in data.CATEGORIES],
    }


@app.get("/api/profile")
def profile():
    u = data.active_user()
    return {
        "name": u["name"], "first_name": u["first_name"], "age": u.get("age"),
        "avatar_color": u["avatar_color"], "household": u.get("household"),
        "address": u.get("address"), "payment": u.get("payment"),
        "dietary": u.get("dietary"),
        "diet_options": ["vegetarian", "vegan", "eggetarian", "keto", "halal", "gluten-free"],
        "allergen_options": ["nuts", "gluten", "dairy", "soy", "shellfish", "eggs"],
    }


class DietaryReq(BaseModel):
    preferences: list[str] = []
    allergens: list[str] = []
    exclude_keywords: list[str] = []


@app.post("/api/profile/dietary")
def update_dietary(req: DietaryReq):
    data.set_dietary(req.model_dump())
    return data.active_user()["dietary"]


@app.get("/api/nextbuy")
def nextbuy():
    return engine.nextbuy()


@app.get("/api/catalog")
def catalog(q: str = "", category: str = "", limit: int = 40):
    return {"products": data.search(q, category, limit)}


@app.get("/api/product/{pid}")
def product(pid: str):
    p = data.product(pid)
    return data.decorate(p) if p else {"error": "not found"}


@app.get("/api/recipes")
def recipes():
    return {"recipes": engine.recipe_list()}


@app.get("/api/recipe/{rid}")
def recipe(rid: str, servings: int = 4):
    r = engine.recipe_scaled(rid, max(1, min(12, servings)))
    return r or {"error": "not found"}


@app.get("/api/speaknow/starters")
def speak_starters():
    return {"chips": data.scenarios()["speaknow"]["starter_chips"]}


@app.get("/api/speaknow")
def speaknow(q: str):
    return engine.speak_resolve(q)


@app.get("/api/speaknow/stream")
async def speaknow_stream(q: str):
    """SSE: kick off agent in background, stream tokens as they arrive,
    then push the final result event. User sees first word in ~1s."""

    async def gen():
        # Run blocking agent in thread pool so we don't block the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, engine.speak_resolve, q)
        
        reply = result.pop("reply", "")
        words = reply.split(" ")
        for i, w in enumerate(words):
            chunk = w + (" " if i < len(words) - 1 else "")
            yield f"event: token\ndata: {json.dumps({'t': chunk})}\n\n"
            await asyncio.sleep(0.025)   # slightly faster word drip
        
        yield f"event: result\ndata: {json.dumps(result)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


class OrderItem(BaseModel):
    product_id: str
    qty: int = 1


class CouponReq(BaseModel):
    items: list[OrderItem]
    payment: str = "upi"


@app.post("/api/coupons")
def coupons(req: CouponReq):
    return engine.evaluate_coupons([i.model_dump() for i in req.items], req.payment)


class OrderReq(BaseModel):
    items: list[OrderItem]
    eta_min: int | None = None
    coupon_code: str | None = None


@app.post("/api/order")
def order(req: OrderReq):
    return engine.create_order([i.model_dump() for i in req.items], req.eta_min, req.coupon_code)


@app.get("/api/orders")
def orders_list():
    return {"orders": engine.order_history()}


@app.get("/api/order/{oid}")
def order_get(oid: str):
    return engine.get_order(oid) or {"error": "not found"}


class GroupCreateReq(BaseModel):
    items: list[OrderItem] = []


class GroupJoinReq(BaseModel):
    name: str


class GroupAddReq(BaseModel):
    product_id: str
    qty: int = 1
    added_by: str


@app.post("/api/group/create")
async def group_create(req: GroupCreateReq):
    u = data.active_user()
    return group.create(u["first_name"], u["avatar_color"],
                        [i.model_dump() for i in req.items])


@app.get("/api/group/{gid}")
def group_get(gid: str):
    return group.enrich(gid) or {"error": "not found"}


@app.post("/api/group/{gid}/join")
async def group_join(gid: str, req: GroupJoinReq):
    return group.join(gid, req.name) or {"error": "not found"}


@app.post("/api/group/{gid}/add")
async def group_add(gid: str, req: GroupAddReq):
    return group.add_item(gid, req.product_id, req.qty, req.added_by) or {"error": "not found"}


@app.post("/api/group/{gid}/checkout")
async def group_checkout(gid: str):
    ok = group.delete_group(gid)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@app.get("/api/group/{gid}/stream")
async def group_stream(gid: str, play: int = 0):
    """SSE: push real-time updates instantly via asyncio.Queue."""
    state = group.enrich(gid)
    if not state:
        async def err():
            yield 'event: error\ndata: {"error":"not found"}\n\n'
        return StreamingResponse(err(), media_type="text/event-stream")

    g = group.get(gid)
    should_play = bool(play) and not g.get("played")
    q = group.subscribe(gid)

    async def gen():
        yield f"event: state\ndata: {json.dumps(state)}\n\n"

        # play scripted timeline if host shared the link
        if should_play:
            g["played"] = True
            elapsed = 0
            for m in group.family_script():
                delay = max(0, m.get("joins_after", 0) - elapsed) / 1000
                await asyncio.sleep(delay)
                elapsed = m.get("joins_after", 0)
                updated = group.play_member(gid, m)
                ev = {"state": updated, "joined": {"name": m["name"], "relation": m.get("relation"),
                                                   "color": m.get("color"), "count": len(m.get("items", []))}}
                yield f"event: update\ndata: {json.dumps(ev)}\n\n"

        # push updates instantly as they happen
        while True:
            raw = await q.get()
            yield f"event: update\ndata: {raw}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/fridge")
def fridge():
    user = data.active_user()
    items = []
    for it in data.fridge()["items"]:
        p = data.product(it["product_id"])
        if p:
            items.append({**it, "product": data.decorate(p, user)})
    return {"updated_label": data.fridge()["updated_label"], "items": items}


@app.get("/api/calendar")
def calendar():
    return data.calendar()


# ---------------------------------------------------------------------------
# AI Dish Recognition  (Issues 2 & 3 — intelligent matching + recipe reuse)
# ---------------------------------------------------------------------------

_IDENTIFY_SYSTEM = """You are a culinary image recognition AI. Respond with ONLY a valid JSON object — no markdown fences, no explanation.

Return exactly:
{"dish_name":"string","cuisine":"string","confidence":number,"error":null}

Set error to a short message if the image is not a recognisable food dish, otherwise null."""

_INGREDIENTS_SYSTEM = """You are a culinary AI for Amazon Now (India). Given a dish name and cuisine, respond with ONLY valid JSON — no markdown, no explanation.

Return exactly:
{"cooking_time_min":number,"base_servings":number,"ingredients":[{"name":"string","qty":number or null,"unit":"string","search_term":"string"}]}

CRITICAL rules for qty and unit:
- qty is the numeric amount (e.g. 500, 2, 0.5) OR null if the ingredient has no numeric quantity.
- unit MUST always be present and non-empty. Use real measurement units: g, kg, ml, L, tsp, tbsp, cups, pcs, pinch, handful, leaves, to taste, etc.
- NEVER return a bare number with an empty unit. Every ingredient must have a unit.
- If the ingredient has no numeric qty (e.g. fresh herbs, garnish), set qty to null and unit to the descriptive text (e.g. "Leaves", "Handful", "To taste", "Few sprigs").
- search_term = simplest grocery search term (e.g. "tomatoes", "eggs", "butter").
- Split compound ingredients (ginger-garlic paste, mixed herbs) into separate purchasable items.
- Quantities scaled to base_servings (usually 4). Dynamic — never hardcoded."""

_DECOMPOSE_SYSTEM = """You are a grocery decomposition AI. Given an ingredient, list which commonly available grocery items are needed to make or substitute it.

Respond ONLY with a valid JSON array of short search strings (e.g. ["garlic","ginger"]).
Return at most 4 items. Return [] if it is already a basic product."""


# ── AI JSON helper (Azure → Bedrock fallback) ────────────────────────────

def _ai_json(messages: list[dict], system: str) -> dict:
    """Call an LLM and parse the response as JSON. Tries Azure first, then Bedrock."""
    raw = ""
    if azure.available():
        try:
            resp = azure.converse(messages, system=system)
            raw = resp["output"]["message"]["content"][0]["text"].strip()
        except Exception as e:
            print(f"[AI JSON] Azure failed: {e}")
    if not raw and bedrock.available():
        try:
            resp = bedrock.converse(messages, system=system)
            raw = resp["output"]["message"]["content"][0]["text"].strip()
        except Exception as e:
            print(f"[AI JSON] Bedrock failed: {e}")
    if raw.startswith("```"):
        raw = "\n".join(ln for ln in raw.splitlines() if not ln.startswith("```")).strip()
    return json.loads(raw)


_IDENTIFY_AND_INGREDIENTS_SYSTEM = """You are a culinary AI for Amazon Now (India).
Look at the food image and respond ONLY with valid JSON — no markdown, no explanation.

Return exactly:
{
  "dish_name": "string",
  "cuisine": "string", 
  "confidence": number,
  "error": null,
  "cooking_time_min": number,
  "base_servings": 4,
  "ingredients": [{"name":"string","qty":number or null,"unit":"string","search_term":"string"}]
}

Rules for ingredients:
- qty is numeric OR null (never empty string)
- unit MUST always be present (g, kg, ml, tsp, tbsp, cups, pcs, pinch, etc.)
- search_term = simplest grocery search term
- Split compound ingredients into separate items
- Set error to a short message if not a food image, else null
- If error is set, ingredients can be []"""


def _identify_and_generate(image_bytes: bytes, media_type: str) -> dict:
    """Single Bedrock call that does both vision ID and ingredient generation."""
    fmt = media_type.split("/")[-1] if "/" in media_type else "jpeg"
    msgs = [{"role": "user", "content": [
        {"image": {"format": fmt, "source": {"bytes": image_bytes}}},
        {"text": "Identify this dish and list all ingredients needed to cook it. Respond ONLY with the JSON as instructed."},
    ]}]
    return _ai_json(msgs, _IDENTIFY_AND_INGREDIENTS_SYSTEM)


def _ai_decompose_batch(ingredient_names: list[str]) -> dict[str, list[str]]:
    """Decompose multiple ingredients in ONE AI call instead of N calls."""
    if not ingredient_names:
        return {}
    try:
        prompt = (
            "For each ingredient below, list which basic grocery items are needed to buy it.\n"
            "Respond ONLY with a JSON object: {ingredient_name: [search_term, ...]}\n"
            "Max 3 items per ingredient. Return [] if it is already a basic product.\n\n"
            + "\n".join(f"- {name}" for name in ingredient_names)
        )
        msgs = [{"role": "user", "content": [{"text": prompt}]}]
        result = _ai_json(msgs, _DECOMPOSE_SYSTEM)
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    return {}


# ── Recipe database matching (Issue 3) ──────────────────────────────────

_RECIPE_STOP = {"the", "and", "for", "with", "recipe", "style", "homemade",
                "easy", "quick", "authentic", "classic"}

_DISH_SYNONYMS: dict[str, list[str]] = {
    "veg chow mein": ["vegetable chow mein", "veg chowmein", "vegetable chowmein", "chow mein"],
    "vegetable chow mein": ["veg chow mein", "veg chowmein", "chow mein"],
    "dal fry": ["daal fry", "dal tadka", "daal tadka"],
    "butter chicken": ["murgh makhani", "chicken makhani"],
    "lamb biryani": ["mutton biryani", "gosht biryani"],
    "palak paneer": ["saag paneer"],
    "rajma": ["rajma masala", "kidney bean curry"],
    "pasta carbonara": ["carbonara", "spaghetti carbonara"],
}


def _norm(text: str) -> str:
    t = re.sub(r"[-–—_]", " ", text.lower())
    t = re.sub(r"[^a-z0-9 ]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _rtoks(name: str) -> set[str]:
    return {t for t in re.split(r"[^a-z]+", _norm(name))
            if len(t) > 2 and t not in _RECIPE_STOP}


def _find_stored_recipe(dish_name: str) -> str | None:
    needle = _norm(dish_name)
    # 1) exact
    for r in data.recipes():
        if _norm(r["name"]) == needle:
            return r["id"]
    # 2) synonyms
    for syn in _DISH_SYNONYMS.get(needle, []):
        for r in data.recipes():
            if _norm(r["name"]) == _norm(syn):
                return r["id"]
    # 3) token overlap >= 60%
    nt = _rtoks(needle)
    best_id, best_ratio = None, 0.0
    for r in data.recipes():
        rt = _rtoks(r["name"])
        if not rt or not nt:
            continue
        ratio = len(nt & rt) / max(len(nt), len(rt))
        if ratio > best_ratio:
            best_ratio, best_id = ratio, r["id"]
    return best_id if best_ratio >= 0.6 else None


# ── Ingredient ↔ product matching (Issue 2) ─────────────────────────────

_ING_SYNONYMS: dict[str, list[str]] = {
    "capsicum": ["bell pepper"], "bell pepper": ["capsicum"],
    "coriander leaves": ["cilantro", "coriander", "dhania"],
    "coriander powder": ["coriander"],
    "curd": ["yogurt", "dahi"], "yogurt": ["curd", "dahi"],
    "maida": ["all purpose flour", "flour"], "all purpose flour": ["maida", "flour"],
    "spring onion": ["scallion", "green onion"], "scallion": ["spring onion"],
    "eggplant": ["brinjal", "aubergine"], "brinjal": ["eggplant", "aubergine"],
    "zucchini": ["courgette"],
    "okra": ["bhindi", "lady finger"], "bhindi": ["okra"],
    "chickpeas": ["chana"], "kidney beans": ["rajma"], "rajma": ["kidney beans"],
    "cottage cheese": ["paneer"], "semolina": ["rava", "sooji"], "rava": ["semolina"],
    "cumin seeds": ["cumin", "jeera"], "cumin": ["jeera"],
    "jeera": ["cumin"], "turmeric": ["haldi"],
    "heavy cream": ["cream"], "sour cream": ["curd", "cream"],
    "chilli powder": ["red chilli powder", "paprika"],
    "paprika": ["red chilli powder", "chilli powder"],
    "parmesan": ["cheese"], "mozzarella": ["cheese"], "cheddar": ["cheese"],
    "breadcrumbs": ["bread"], "cream cheese": ["cheese"],
    "chicken breast": ["chicken", "boneless chicken"],
    "chicken thighs": ["chicken"], "pork chops": ["pork"],
    "shrimp": ["prawns"], "prawns": ["shrimp"],
    "salmon": ["fish"], "tuna": ["fish"],
    "pasta": ["spaghetti", "penne"],
    "spaghetti": ["pasta"], "noodles": ["egg noodles"],
    "soy sauce": ["soya sauce"], "rice vinegar": ["white vinegar"],
    "fish sauce": ["soy sauce"], "oyster sauce": ["soy sauce"],
    "cilantro": ["coriander", "dhania"],
    "greek yogurt": ["yogurt", "curd"],
    "corn flour": ["cornstarch"], "cornstarch": ["corn flour"],
    "baking soda": ["baking powder"],
    "vanilla extract": ["vanilla essence"],
    "coconut milk": ["coconut", "coconut cream"],
    "tahini": ["sesame seeds"],
}

_COMPOUND: dict[str, list[str]] = {
    "ginger garlic paste": ["ginger", "garlic"],
    "ginger-garlic paste": ["ginger", "garlic"],
    "mixed herbs": ["oregano", "basil", "thyme"],
    "italian seasoning": ["oregano", "thyme", "rosemary", "basil"],
    "taco seasoning": ["chilli powder", "paprika", "cumin"],
    "fajita seasoning": ["cumin", "paprika", "chilli powder"],
    "cajun seasoning": ["paprika", "garlic powder"],
    "panko breadcrumbs": ["breadcrumbs", "bread"],
    "bread crumbs": ["breadcrumbs", "bread"],
    "tomato puree": ["tomatoes"],
    "tomato paste": ["tomatoes"],
    "sushi vinegar": ["rice vinegar", "sugar", "salt"],
    "teriyaki sauce": ["soy sauce", "sugar"],
    "worcestershire sauce": ["soy sauce"],
    "hot sauce": ["chilli sauce"],
    "sriracha": ["chilli sauce"],
    "hoisin sauce": ["soy sauce"],
    "miso paste": ["soy sauce"],
    "salted butter": ["butter"], "unsalted butter": ["butter"],
    "clarified butter": ["ghee", "butter"],
    "whole milk": ["milk"], "skimmed milk": ["milk"],
    "buttermilk": ["milk", "curd"],
    "double cream": ["cream"], "whipping cream": ["cream"],
    "chicken stock": ["chicken broth"], "chicken broth": ["chicken"],
    "vegetable stock": ["vegetables"],
    "self raising flour": ["flour", "baking powder"],
    "almond flour": ["almonds"],
    "vanilla extract": ["vanilla essence"],
    "pizza dough": ["flour", "yeast"],
    "five spice powder": ["cinnamon", "cloves"],
    "curry powder": ["turmeric", "coriander", "cumin"],
    "garam masala blend": ["garam masala"],
    "herbes de provence": ["thyme", "rosemary", "oregano"],
}


def _fuzzy_norm(term: str) -> str:
    t = re.sub(r"[-–_]", " ", term.lower().strip())
    t = re.sub(r"[^a-z0-9 ]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if t.endswith("es") and len(t) > 4:
        t = t[:-2]
    elif t.endswith("s") and len(t) > 3:
        t = t[:-1]
    return t


def _try_get_product(term: str) -> dict | None:
    hits = data.retrieve(term, limit=3)
    if hits:
        full = data.product(hits[0]["id"])
        if full:
            return data.decorate(full, data.active_user())
    return None


def _best_product(term: str) -> dict | None:
    # 1. direct
    p = _try_get_product(term)
    if p:
        return p
    # 2. extended synonyms
    fn = _fuzzy_norm(term)
    for syn in _ING_SYNONYMS.get(fn, []):
        p = _try_get_product(syn)
        if p:
            return p
    # 3. fuzzy normalised
    if fn != term.lower().strip():
        p = _try_get_product(fn)
        if p:
            return p
    # 4. individual words
    words = [w for w in fn.split() if len(w) > 2]
    if len(words) > 1:
        for w in words:
            p = _try_get_product(w)
            if p:
                return p
    return None





def _build_display_qty(ing: dict) -> str:
    qty = ing.get("qty")
    unit = (ing.get("unit") or "").strip()
    if qty is not None and unit:
        return f"{qty:g} {unit}".strip()
    if qty is not None:
        return f"{qty:g} pcs"
    if unit:
        return unit
    return ing.get("display_qty", "").strip() or "as needed"


def _map_single_ingredient(ing: dict) -> list[dict]:
    name = ing.get("name", "")
    search_term = ing.get("search_term") or name
    qty = ing.get("qty")
    unit = (ing.get("unit") or "").strip()
    display_qty = _build_display_qty(ing)

    def line(n: str, prod: dict | None) -> dict:
        return {"name": n, "display_qty": display_qty, "qty": qty, "unit": unit,
                "search_term": search_term, "product": prod,
                "price": prod["price"] if prod else 0, "available": prod is not None}

    fn_name = _fuzzy_norm(name)
    fn_search = _fuzzy_norm(search_term)

    # 1-2-5-6: direct + synonym + fuzzy + word parts
    prod = _best_product(search_term)
    if prod:
        return [line(name, prod)]
    if fn_name != fn_search:
        prod = _best_product(name)
        if prod:
            return [line(name, prod)]

    # 3: static compound decomposition
    comps = _COMPOUND.get(fn_name) or _COMPOUND.get(fn_search)
    if comps:
        lines = [line(c.title(), _best_product(c)) for c in comps]
        if any(l["available"] for l in lines):
            return lines

    # 4: AI decomposition
    parts = _ai_decompose(name)
    if parts:
        lines = [line(p.title(), _best_product(p)) for p in parts]
        if any(l["available"] for l in lines):
            return lines

    return [line(name, None)]


def _map_ingredients_to_products(ingredients: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple] = set()
    
    # First pass — map without AI decomposition
    unmatched_names = []
    first_pass = []
    for ing in ingredients:
        lines = _map_single_ingredient(ing)
        first_pass.append((ing, lines))
        if all(not ln["available"] for ln in lines):
            unmatched_names.append(ing.get("name", ""))
    
    # ONE batch AI call for all unmatched ingredients
    decomposed = _ai_decompose_batch(unmatched_names) if unmatched_names else {}
    
    # Second pass — apply decomposition results
    for ing, lines in first_pass:
        name = ing.get("name", "")
        if all(not ln["available"] for ln in lines) and name in decomposed:
            parts = decomposed[name]
            new_lines = []
            for p_name in parts:
                prod = _best_product(p_name)
                if prod:
                    display_qty = _build_display_qty(ing)
                    new_lines.append({
                        "name": name, "display_qty": display_qty,
                        "qty": ing.get("qty"), "unit": ing.get("unit", ""),
                        "search_term": p_name, "product": prod,
                        "price": prod["price"], "available": True
                    })
            if new_lines:
                lines = new_lines

        for ln in lines:
            pid = ln["product"]["id"] if ln["product"] else None
            key = (ln["name"].lower().strip(), pid or "")
            if key in seen:
                continue
            seen.add(key)
            result.append(ln)
    
    return result

def _recipe_to_dish_analysis(recipe: dict) -> dict:
    """
    Convert a recipe_scaled() result to the DishAnalysis response shape.
    Preserves display_qty, base_measure, and all ingredient rows exactly —
    including multiple rows for the same product (e.g. garlic 2 tsp + 4 whole).
    No deduplication, no normalisation, no unit replacement.
    """
    ingredients = []
    for ing in recipe.get("ingredients", []):
        p = ing.get("product")
        # display_qty is already built correctly by engine.recipe_scaled:
        #   "{scaled_qty:g} {unit}" when qty is not null, else ing["measure"]
        display_qty = ing.get("display_qty", "") or ing.get("base_measure", "")
        ingredients.append({
            "name": ing.get("name", ""),
            "display_qty": display_qty,
            # Keep base_measure as the canonical unit text so the frontend
            # scaleDisplayQty helper receives something meaningful.
            "qty": ing.get("qty") if ing.get("qty") is not None else None,
            "unit": ing.get("base_measure", ""),
            "search_term": ing.get("name", ""),
            "product": p,
            "price": ing.get("price", 0),
            "available": p is not None,
        })
    return {
        "dish_name": recipe["name"],
        "cuisine": recipe.get("cuisine", ""),
        "cooking_time_min": recipe.get("time_min", 30),
        "base_servings": recipe.get("base_servings", 4),
        "ingredients": ingredients,
        "ingredient_count": len(ingredients),
        "image": recipe.get("image"),
        "from_stored_recipe": True,
        "recipe_id": recipe.get("id"),
    }


_ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
_MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@app.post("/api/dish/analyze")
async def dish_analyze(image: UploadFile = File(...)):
    content_type = (image.content_type or "").lower()
    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image format '{content_type}'.")

    image_bytes = await image.read()
    if len(image_bytes) > _MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 5 MB).")
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty image file.")

    # ONE call: vision ID + ingredient generation combined
    try:
        dish_info = _identify_and_generate(image_bytes, content_type)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="AI returned unexpected response. Please try again.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {str(e)}")

    if dish_info.get("error"):
        raise HTTPException(status_code=422, detail=dish_info["error"])

    dish_name: str = dish_info.get("dish_name", "")
    cuisine: str = dish_info.get("cuisine", "")
    if not dish_name:
        raise HTTPException(status_code=422, detail="Could not identify a dish. Please try a clearer food photo.")

    # Check stored recipe first — skip AI ingredients if we have one
    recipe_id = _find_stored_recipe(dish_name)
    if recipe_id:
        from . import engine as _eng
        recipe = _eng.recipe_scaled(recipe_id, 4)
        if recipe:
            return _recipe_to_dish_analysis(recipe)

    # Use the ingredients already returned in the same call
    ingredients_raw = dish_info.get("ingredients", [])
    if not ingredients_raw:
        raise HTTPException(status_code=422, detail="No ingredients detected. Please try a clearer photo.")

    mapped = _map_ingredients_to_products(ingredients_raw)
    return {
        "dish_name": dish_name,
        "cuisine": cuisine,
        "cooking_time_min": dish_info.get("cooking_time_min", 30),
        "base_servings": max(1, int(dish_info.get("base_servings", 4))),
        "ingredients": mapped,
        "ingredient_count": len(mapped),
        "from_stored_recipe": False,
    }