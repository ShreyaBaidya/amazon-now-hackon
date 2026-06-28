"""Amazon Now demo API — config-driven, deterministic, no external LLM at runtime."""
from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import bedrock, data, engine, group

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


@app.get("/api/nowcast")
def nowcast():
    return engine.nowcast()


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


@app.get("/api/nowspeak/starters")
def speak_starters():
    return {"chips": data.scenarios()["nowspeak"]["starter_chips"]}


@app.get("/api/nowspeak")
def nowspeak(q: str):
    return engine.speak_resolve(q)


@app.get("/api/nowspeak/stream")
async def nowspeak_stream(q: str):
    """SSE: stream the reply word-by-word, then a final 'result' event with products."""
    result = engine.speak_resolve(q)
    reply = result.pop("reply", "")

    async def gen():
        words = reply.split(" ")
        for i, w in enumerate(words):
            chunk = w + (" " if i < len(words) - 1 else "")
            yield f"event: token\ndata: {json.dumps({'t': chunk})}\n\n"
            await asyncio.sleep(0.035)
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
