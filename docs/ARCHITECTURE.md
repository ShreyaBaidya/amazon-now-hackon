# Amazon Now — Target Architecture

Architecture of the **scaled, production-grade** system once the demo's hardcoded
config is replaced by live services. Vendor-neutral — logical services and data
ownership only, no deployment topology.

Two views:

1. **[Logical architecture](#1-logical-architecture)** — services, boundaries, data ownership.
2. **[Functional architecture](#2-functional-architecture)** — user-facing features and the flows that power them.

The governing idea: the store flips from **search-first** to **intent-first**.
Two intelligence services (predict / converse) sit in front of a conventional
commerce core (catalog, pricing, orders). Intelligence is **bounded** — the LLM
only ranks/selects over retrieved real data; deterministic code owns safety,
pricing, and money.

---

## 1. Logical architecture

### 1.1 System map

```
                    ┌──────────────────────────────────────┐
                    │  CLIENTS   PWA · Voice · Push          │
                    └─────────────────┬────────────────────┘
                                      │ HTTPS · WSS · SSE
                    ┌─────────────────▼────────────────────┐
                    │  EDGE / CDN   assets · images · TLS · WAF
                    └─────────────────┬────────────────────┘
                    ┌─────────────────▼────────────────────┐
                    │  API GATEWAY  authn · rate-limit · SSE fan
                    └──┬──────┬──────┬──────┬──────┬────────┘
                       │      │      │      │      │
        ┌──────────────┘      │      │      │      └──────────────┐
        ▼                     ▼      ▼      ▼                     ▼
 ┌────────────┐    ┌────────────────┐ ┌───────┐ ┌──────────┐ ┌────────────┐
 │ PREDICTION │    │ AGENT          │ │CATALOG│ │ PRICING/ │ │ ORDER/     │
 │ (NowCast)  │    │ (NowSpeak)     │ │SEARCH │ │ PROMO    │ │ FULFIL     │
 └─────┬──────┘    └──────┬─────────┘ └───┬───┘ └────┬─────┘ └─────┬──────┘
       │            ┌─────▼──────┐        │          │       ┌─────▼──────┐
       │            │ LLM INFER  │        │          │       │ GROUP CART │
       │            │ + vector   │        │          │       │ (realtime) │
       │            │ retrieval  │        │          │       └────────────┘
       │            └────────────┘        │          │
       ▼                                  ▼          ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │ DATA LAYER  catalog · vector index · profile · signals · orders · │
 │             cart cache · event log · object store                  │
 └──────────────────────────────────────────────────────────────────┘
                              ▲
                  ┌───────────┴──────────┐
                  │ INGESTION / SIGNALS   │
                  │ fridge · calendar ·   │
                  │ purchase events       │
                  └───────────────────────┘
```

### 1.2 Service boundaries

| Service | Owns | Gap from current demo |
|---|---|---|
| **Prediction (NowCast)** | fuse signals → ranked explainable triggers | logic real; needs **live feeds**, not static config |
| **Agent (NowSpeak)** | NL / list / link / voice → structured cart intent | **biggest gap** — keyword match → LLM + retrieval |
| **Catalog / Search** | product corpus, lexical + semantic search | static JSON → indexed store + vector index |
| **Pricing / Promo** | coupon eval, best-offer pick | already real; needs live coupon source |
| **Order / Fulfil** | order lifecycle, ETA, rider tracking | in-memory → persisted, event-driven |
| **Group cart** | shared cart, live merge | needs real pub/sub fan-out |

### 1.3 NowSpeak — the agent loop

```
user query ─┐
            ▼
   ┌──────────────┐  pre-parse: URL? list? voice transcript?
   │ INPUT ROUTER │──────────────┐ (deterministic fast-paths)
   └──────┬───────┘              ▼
          │ free-form NL   ┌───────────────┐
          ▼                │ URL FETCH +   │
   ┌──────────────┐        │ recipe extract│
   │ RETRIEVAL    │        └───────┬───────┘
   │ vector+lexical│               │
   │ over catalog  │               │
   └──────┬───────┘                │
          ▼                        │
   ┌──────────────┐◄───────────────┘
   │ LLM tool-use │  grounded ONLY on retrieved candidate ids
   │ →{reply,     │  (no hallucinated SKUs)
   │   product_ids,│
   │   recipe_id?, │
   │   dietary_note}│
   └──────┬───────┘
          ▼
   ┌──────────────┐  HARD safety gate — code, not prompt-trust:
   │ ALLERGEN     │  drop any product w/ allergen_conflict
   │ GUARD        │  for the active profile
   └──────┬───────┘
          ▼
   ┌──────────────┐
   │ CART ASSEMBLY│  prices · qty · scaling · totals  ← already real
   └──────┬───────┘
          ▼ streamed SSE
       client
```

**Principle: LLM proposes from retrieved candidates, deterministic code disposes.**
Hallucination-proof (only real SKUs survive) and allergy-safe (the gate is code).

### 1.4 NowCast — signals → predicted cart

```
 calendar    fridge    purchase log    live feeds → SIGNALS STORE
    │          │            │
    ▼          ▼            ▼
 ┌──────────────────────────────┐
 │ FUSION ENGINE                 │
 │ calendar→event needs (scaled) │
 │ fridge→out/low flags          │
 │ history→cadence (reorder due) │  ← logic already real
 │ merge·priority·explain        │
 └──────────────┬────────────────┘
                ▼ ranked groups + human reason
             client (one-tap build)
```

Cadence upgrade path: static `avg_interval_days` → **learned per-user reorder
model** off the event log.

### 1.5 Data ownership

| Store | Holds | Profile |
|---|---|---|
| Catalog DB | products, dietary/allergen tags | read-heavy |
| Vector index | embeddings of products + recipes | semantic match |
| User profile | persona, dietary, allergens, address | consistency-critical |
| Signals store | fridge · calendar · purchase events | time-series append |
| Orders | lifecycle, immutable history | durable, audited |
| Cart cache | active + group carts | low-latency TTL |
| Event log | all domain events | source of truth → replay |
| Object store | product/recipe imagery | CDN-fronted |

### 1.6 Cross-cutting

- **observability** — traces across the agent loop (retrieval → LLM → guard), latency budgets
- **resilience** — LLM timeout → fallback to lexical search (graceful degrade, never broken)
- **caching** — embedding cache · prediction cache (per-user, short TTL)
- **realtime** — pub/sub for group-cart fan-out + order tracking
- **security** — allergen guard is a non-bypassable server-side gate
- **cost** — retrieve-then-prompt keeps LLM context small (only candidate SKUs)

---

## 2. Functional architecture

Feature-first view: what the user does, and which capabilities each surface
depends on. Same services as above, organized by user journey instead of by tier.

### 2.1 Feature map

```
┌────────────────────────────────────────────────────────────────────┐
│                          AMAZON NOW                                  │
│                                                                      │
│  DISCOVER ───────────────► DECIDE ───────────────► BUY              │
│                                                                      │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐   │
│  │ NowCast      │   │ NowSpeak     │   │ Cart & Checkout       │   │
│  │ predictive   │   │ conversational│   │                       │   │
│  │ home         │   │ agent        │   │ • best-coupon auto    │   │
│  │              │   │              │   │ • compare/switch offer│   │
│  │ • calendar   │   │ • natural lang│   │ • place order         │   │
│  │ • fridge     │   │ • pasted list │   └───────────┬───────────┘   │
│  │ • cadence    │   │ • recipe link │               │               │
│  │ • 1-tap build│   │ • voice       │   ┌───────────▼───────────┐   │
│  └──────┬───────┘   └──────┬───────┘   │ Order tracking         │   │
│         │                  │           │ • ETA countdown        │   │
│         │   ┌──────────────┤           │ • moving rider         │   │
│         │   │              │           └───────────────────────┘   │
│         │   ▼              ▼                                         │
│         │ ┌──────────────┐ ┌──────────────┐                        │
│         └►│ Cook         │ │ Group cart    │                        │
│           │ • recipe     │ │ • shared cart │                        │
│           │   gallery    │ │ • invite link │                        │
│           │ • serving    │ │ • live merge  │                        │
│           │   scaling    │ │   as members  │                        │
│           │ • add all    │ │   join        │                        │
│           └──────┬───────┘ └──────────────┘                        │
│                  │                                                   │
│         ┌────────▼────────┐                                         │
│         │ Reorder         │  past orders → refill cart 1-tap        │
│         └─────────────────┘                                         │
│                                                                      │
│  CROSS-CUTTING:  Dietary & allergen safety enforced everywhere      │
│                  Profile (diet, allergens, address) feeds all flows │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Feature → capability matrix

Which backend capability each feature leans on. Shows how few primitives power
the whole product — and that **dietary safety is shared by all of them**.

| Feature | Predict | Retrieval | LLM | Pricing | Realtime | Dietary guard |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| NowCast home | ● | | | | | ● |
| NowSpeak (NL) | | ● | ● | | | ● |
| NowSpeak (list) | | ● | | | | ● |
| NowSpeak (link) | | ● | ● | | | ● |
| Cook / recipes | | ● | | | | ● |
| Group cart | | | | | ● | ● |
| Checkout | | | | ● | | |
| Order tracking | | | | | ● | |
| Reorder | | | | | | ● |

### 2.3 The core journey — "intent to delivered cart"

```
 trigger                resolution              commit
 ───────                ──────────              ──────
 NowCast tap   ─┐
                ├─► assembled cart ─► review ─► best coupon ─► place ─► track
 NowSpeak ask  ─┘    (real SKUs,       (edit    auto-applied   order   ETA +
 Cook add-all  ─┘     priced, diet-     qty)     (switchable)           rider
 Reorder       ─┘     safe)
```

Every entry point converges on **one assembled-cart contract**:
`{ product_ids[], qty, recipe_id?, dietary_note }`. That single shape is why
prediction, conversation, recipes and reorder all reuse the same pricing,
safety, and checkout pipeline downstream.

### 2.4 Safety as a cross-cutting feature

Dietary and allergen enforcement is **not** a feature of one screen — it's a gate
every cart-producing flow passes through, enforced server-side in code (never
prompt-trust). A vegan profile or a nut allergy filters NowCast predictions,
NowSpeak resolutions, recipe ingredients, and reorders identically.

```
any cart-producing flow ──► [ DIETARY / ALLERGEN GUARD ] ──► cart
                              reads active profile;
                              drops/flags conflicts;
                              non-bypassable
```
