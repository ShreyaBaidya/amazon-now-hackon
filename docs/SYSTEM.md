# Amazon Now — System Documentation

Documents the **system as it runs today**: processes, modules, data files, the
HTTP/SSE API, and the request flows behind each feature. For the future scaled
design see [`ARCHITECTURE.md`](./ARCHITECTURE.md).

The intelligence layer fuses live signals, resolves natural-language intent, and
prices carts through explainable, deterministic logic — every prediction and
resolution carries a human-readable reason. This doc describes the running system
end to end.

---

## 1. Runtime topology

Two processes, talking over REST + Server-Sent Events.

```
┌──────────────────────────────┐         ┌──────────────────────────────┐
│  FRONTEND  (Next.js 16 PWA)   │  HTTP   │  BACKEND  (FastAPI / uvicorn) │
│  localhost:3100               │ ──────► │  127.0.0.1:8010               │
│                               │  SSE    │                               │
│  src/lib/api.ts  ── client ──►│ ◄────── │  app/main.py  ── routes       │
└──────────────────────────────┘         └───────────────┬──────────────┘
                                                          │ reads
                                                          ▼
                                          ┌──────────────────────────────┐
                                          │  /config/*.json  (data store) │
                                          └──────────────────────────────┘
```

- **Frontend → backend base URL:** `NEXT_PUBLIC_API_BASE` (default `http://127.0.0.1:8010`).
- **CORS:** backend allows all origins/methods/headers (demo).
- **State:** orders and group carts live **in-memory** (process lifetime only);
  everything else is read from `/config` and cached with `lru_cache`.

---

## 2. Backend modules (nodes)

| Module | Responsibility | Key exports |
|---|---|---|
| `app/main.py` | HTTP/SSE routes, request models | FastAPI `app`, all endpoints |
| `app/engine.py` | Core logic: NextBuy fusion, recipe scaling, SpeakNow resolve, coupons, orders | `nextbuy`, `recipe_scaled`, `speak_resolve`, `evaluate_coupons`, `create_order`, `order_history` |
| `app/group.py` | In-memory group ("shop together") carts + scripted live-fill | `create`, `join`, `add_item`, `enrich`, `play_member` |
| `app/data.py` | Config loading, catalog index, search, dietary/allergen decoration | `catalog`, `product`, `search`, `decorate`, `active_user`, `set_dietary` |

### Module dependency

```
main.py ──► engine.py ──► data.py ──► /config/*.json
   │                         ▲
   └──────► group.py ────────┘
```

`data.py` is the only module that touches disk. `engine.py` and `group.py` are
pure logic over `data.py`. `main.py` is a thin HTTP shell — no business logic.

---

## 3. Data store (`/config`)

Loaded once per process, memoized via `lru_cache`.

| File | Holds | Read by |
|---|---|---|
| `catalog.json` | products (`id`, `name`, `brand`, `price`, `category`, `rating`, `dietary_tags`, `allergen_tags`, `match_key`) | `data.catalog` |
| `recipes.json` | recipes (`ingredients` → `product_id`, `qty`, `unit`, `steps`, `base_servings`) | `data.recipes` |
| `fridge.json` | smart-fridge items + `status` (`out`/`low`/ok), `updated_label` | NextBuy, `/api/fridge` |
| `history.json` | purchase `cadence` (avg interval, last ordered) + `recent_orders` | NextBuy, order history |
| `calendar.json` | events; the `is_hero` event carries `needs` (product_id, qty, reason) | NextBuy, `/api/calendar` |
| `coupons.json` | coupons (`type`: flat/percent/category_percent/free_delivery, eligibility) | coupon engine |
| `personas.json` | users; `active_user` pointer; per-user `dietary` (prefs, allergens) | `data.active_user` |
| `family.json` | scripted group members + their picks + `joins_after` (ms) | group live-fill |
| `scenarios.json` | SpeakNow scripted `intents` (`match` keywords → reply + product_ids/recipe), `starter_chips`, `fallback_reply` | SpeakNow |
| `settings.json` | `demo_now`, `eta_default_min`, `delivery_fee`, `free_delivery_above`, `reorder_due_ratio`, `dark_store` | many |

Build pipeline (`/scripts`): `build_catalog.py` (hero products + imagery),
`build_recipes.py` (recipe corpus + long-tail catalog).

---

## 4. HTTP API reference

Base: `http://127.0.0.1:8010`. All JSON unless noted. `●` = in-memory write.

### Shell / profile

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | — | `{ok, products, recipes}` |
| GET | `/api/bootstrap` | — | settings + active user + categories |
| GET | `/api/profile` | — | full profile + diet/allergen option lists |
| POST | `/api/profile/dietary` ● | `{preferences[], allergens[], exclude_keywords[]}` | updated dietary block (runtime override) |

### NextBuy (predictive home)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/nextbuy` | greeting + grouped triggers (calendar/fridge/history), totals, ETA |
| GET | `/api/fridge` | fridge items decorated with products |
| GET | `/api/calendar` | raw calendar events |

### Catalog / recipes

| Method | Path | Params | Returns |
|---|---|---|---|
| GET | `/api/catalog` | `q`, `category`, `limit=40` | `{products[]}` (scored search) |
| GET | `/api/product/{pid}` | — | decorated product |
| GET | `/api/recipes` | — | `{recipes[]}` summaries |
| GET | `/api/recipe/{rid}` | `servings=4` (clamped 1–12) | scaled recipe + priced ingredients |

### SpeakNow (agent)

| Method | Path | Params | Returns |
|---|---|---|---|
| GET | `/api/speaknow/starters` | — | `{chips[]}` |
| GET | `/api/speaknow` | `q` | `{reply, products[], recipe?, note, total, dietary_note?}` |
| GET | `/api/speaknow/stream` | `q` | **SSE**: `token`* → `result` → `done` |

### Coupons / orders

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/coupons` | `{items[], payment="upi"}` | `{subtotal, delivery_fee, best_code, coupons[]}` |
| POST | `/api/order` ● | `{items[], eta_min?, coupon_code?}` | created order |
| GET | `/api/orders` | — | `{orders[]}` past delivered (from history) |
| GET | `/api/order/{oid}` | — | live order or `{error}` |

`items[]` element: `{product_id, qty=1}`.

### Group cart ("shop together")

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/group/create` ● | `{items[]}` | new group (host = active user) |
| GET | `/api/group/{gid}` | — | enriched group state |
| POST | `/api/group/{gid}/join` ● | `{name}` | state with new member |
| POST | `/api/group/{gid}/add` ● | `{product_id, qty=1, added_by}` | state with item |
| GET | `/api/group/{gid}/stream` | `play=0\|1` | **SSE**: `state` → `update`* (if play) → `done` |

---

## 5. SSE event contracts

### `GET /api/speaknow/stream?q=...`

Reply resolved server-side, then streamed word-by-word (~35 ms/word).

```
event: token   data: {"t": "Got "}      (one per word)
event: token   data: {"t": "your "}
...
event: result  data: { products, recipe, note, total, ... }   (reply removed)
event: done    data: {}
```

### `GET /api/group/{gid}/stream?play=1`

Emits current state, then — only on first `play=1` — replays the scripted family
joining on each member's `joins_after` timer.

```
event: state   data: { full enriched group }
event: update  data: { state, joined: {name, relation, color, count} }   (per member)
event: done    data: {}
```

`play` is one-shot: guarded by `g["played"]` so a refresh won't replay.

---

## 6. Feature flows

### NextBuy — predicted cart (`engine.nextbuy`)

```
fridge.json (out/low)  ─┐
history.json (cadence) ─┼─► raw signals ─► merge by product ─► group by signal ─► ranked cart
calendar.json (hero)   ─┘   (each w/ reason)  (dedup, keep      (calendar>fridge   + greeting,
                                               highest priority,  >history)          totals, ETA
                                               collect reasons)
```

- **Reorder-due test:** `last_ordered_days_ago >= avg_interval_days * reorder_due_ratio`.
- **Calendar:** hero event's `needs` become lines (headcount-scaled `qty` baked into config).
- Each line carries human `reasons[]` — predictions are explainable.

### SpeakNow — request → cart (`engine.speak_resolve`)

Deterministic priority ladder (first match wins):

```
query
  │
  ├─ 1. contains URL?      → match recipe by link text → scaled recipe + ingredients
  ├─ 2. has comma/newline? → split list → _best_match each term to a product
  ├─ 3. scripted intent?   → keyword in scenarios.json intents → canned reply + product_ids/recipe
  ├─ 4. dish name match?   → _match_recipe (token overlap) → scaled recipe
  └─ 5. fallback           → catalog search (data.search)
```

Each tier resolves the input to real, priced products and (where relevant) a
scaled recipe, with a human-readable `reply`. The
[target design](./ARCHITECTURE.md#13-speaknow--the-agent-loop) extends this same
contract with retrieval + LLM tool-use behind tiers 3–5, keeping the URL and
list fast-paths deterministic.

### Coupons — auto best offer (`engine.evaluate_coupons`)

```
items ─► subtotal + per-category totals ─► for each coupon: eligible? discount?
      ─► sort (eligible desc, discount desc) ─► best_code = first eligible w/ discount>0
```

Discount types: `flat`, `percent` (capped), `category_percent` (capped), `free_delivery`.
Eligibility checks: `min_order`, `payment` match, category presence, delivery already free.

### Group cart — live fill (`group.py`)

```
create (host)  ─► join / add_item (manual)
                       │
                  enrich(gid): price lines, per-member subtotals, totals
                       │
   stream?play=1 ─► play_member() per family.json entry on joins_after timer ─► update events
```

### Order lifecycle (`engine.create_order`)

```
items + coupon_code ─► price lines ─► apply delivery fee (free above threshold)
                    ─► apply best coupon discount ─► store in _ORDERS[oid]
                    ─► stages: placed → packing → out for delivery → arriving
```

IDs: live orders `AN1001+` (sequential), history orders `AN9000+`.

---

## 7. Cross-cutting: dietary / allergen safety

`data.decorate(product, user)` runs on **every product** leaving the API. It
reads the active user's `dietary` block and attaches:

- `warnings[]` — e.g. `"Contains nuts"`, `"Not vegan"`, `"Not vegetarian"`.
- `allergen_conflict: bool` — true if any allergen tag intersects user allergens.

The Profile screen can override the active dietary profile at runtime via
`POST /api/profile/dietary` (`data.set_dietary`), and every subsequent decorated
response reflects it. This is the real, shared safety layer across NextBuy,
SpeakNow, recipes, catalog, and group carts.

---

## 8. Running locally

```bash
# API tier
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010

# Storefront (new terminal)
cd frontend
pnpm install
pnpm exec next dev -p 3100      # open http://localhost:3100 (renders as a phone)
```

Tests: `cd backend && uv run pytest -q` · `cd frontend && pnpm exec playwright test`.
