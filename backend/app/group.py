"""In-memory group ('shop together') carts with push-based SSE notifications."""
from __future__ import annotations

import asyncio
import json

from . import data

_GROUPS: dict[str, dict] = {}
_SEQ = [1000]
_SUBSCRIBERS: dict[str, list[asyncio.Queue]] = {}


def subscribe(gid: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _SUBSCRIBERS.setdefault(gid, []).append(q)
    return q


def unsubscribe(gid: str, q: asyncio.Queue) -> None:
    subs = _SUBSCRIBERS.get(gid)
    if subs:
        subs.remove(q)


def _bump(gid: str) -> None:
    state = enrich(gid)
    if not state:
        return
    subs = _SUBSCRIBERS.get(gid, [])
    dead = []
    for q in subs:
        try:
            q.put_nowait(json.dumps({"state": state}))
        except asyncio.QueueFull:
            dead.append(q)
        except Exception:
            dead.append(q)
    for q in dead:
        unsubscribe(gid, q)


def _palette(i: int) -> str:
    return ["#FF9900", "#7C3AED", "#0EA5E9", "#714C0D", "#067d62", "#e11d48"][i % 6]


def create(host_name: str, host_color: str, seed_items: list[dict] | None = None) -> dict:
    _SEQ[0] += 1
    gid = f"FAM{_SEQ[0]}"
    g = {
        "id": gid,
        "code": gid,
        "host": host_name,
        "members": [{"name": host_name, "color": host_color, "relation": "You", "host": True}],
        "items": [],
        "played": False,
    }
    _GROUPS[gid] = g
    for it in seed_items or []:
        _add_item(g, it["product_id"], it.get("qty", 1), host_name)
    _bump(gid)
    return enrich(gid)


def get(gid: str) -> dict | None:
    return _GROUPS.get(gid)


def _member(g: dict, name: str, color: str, relation: str) -> None:
    if not any(m["name"] == name for m in g["members"]):
        g["members"].append({"name": name, "color": color, "relation": relation, "host": False})


def join(gid: str, name: str) -> dict | None:
    g = _GROUPS.get(gid)
    if not g:
        return None
    _member(g, name, _palette(len(g["members"])), "Family")
    _bump(gid)
    return enrich(gid)


def _add_item(g: dict, product_id: str, qty: int, added_by: str) -> None:
    p = data.product(product_id)
    if not p:
        return
    ex = next((i for i in g["items"] if i["product_id"] == product_id and i["added_by"] == added_by), None)
    if ex:
        ex["qty"] = max(0, ex["qty"] + qty)
        if ex["qty"] <= 0:
            g["items"].remove(ex)
    elif qty > 0:
        g["items"].append({"product_id": product_id, "qty": qty, "added_by": added_by})


def add_item(gid: str, product_id: str, qty: int, added_by: str) -> dict | None:
    g = _GROUPS.get(gid)
    if not g:
        return None
    _add_item(g, product_id, qty, added_by)
    _bump(gid)
    return enrich(gid)


def enrich(gid: str) -> dict | None:
    g = _GROUPS.get(gid)
    if not g:
        return None
    color_of = {m["name"]: m["color"] for m in g["members"]}
    items, total, count = [], 0, 0
    by_member = {m["name"]: 0 for m in g["members"]}
    for it in g["items"]:
        if it.get("qty", 0) <= 0:
            continue
        p = data.product(it["product_id"])
        if not p:
            continue
        line = p["price"] * it["qty"]
        total += line
        count += it["qty"]
        by_member[it["added_by"]] = by_member.get(it["added_by"], 0) + line
        items.append({
            "product": data.decorate(p),
            "qty": it["qty"],
            "added_by": it["added_by"],
            "added_by_color": color_of.get(it["added_by"], "#565959"),
            "line_total": line,
        })
    members = [{**m, "subtotal": by_member.get(m["name"], 0),
               "item_count": sum(i["qty"] for i in g["items"] if i["added_by"] == m["name"])}
              for m in g["members"]]
    return {
        "id": g["id"], "code": g["code"], "host": g["host"],
        "members": members, "items": items,
        "item_count": count, "total": total,
    }


def family_script() -> list[dict]:
    fam = data.family()["members"]
    return sorted(fam, key=lambda m: m.get("joins_after", 0))


def play_member(gid: str, member: dict) -> dict | None:
    g = _GROUPS.get(gid)
    if not g:
        return None
    _member(g, member["name"], member.get("color", "#7C3AED"), member.get("relation", "Family"))
    for it in member.get("items", []):
        _add_item(g, it["product_id"], it.get("qty", 1), member["name"])
    _bump(gid)
    return enrich(gid)


def delete_group(gid: str) -> bool:
    """Delete a group cart. Returns True if it existed."""
    if gid not in _GROUPS:
        return False
    del _GROUPS[gid]
    _SUBSCRIBERS.pop(gid, None)
    return True
