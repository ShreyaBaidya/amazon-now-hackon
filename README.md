# Amazon Now — Reimagining Urgent Shopping

> **Stop searching. It's already in your cart.**

Amazon Now is a quick-commerce experience built for the moments when shopping has to be instant — you discover, decide, and buy what you need in seconds, not minutes. Instead of a search box and endless browsing, Amazon Now puts an intelligent agent at the front of the store that understands your context and assembles the cart for you.

Built for **Hackon with Amazon 6.0**.

---

## The idea

Urgent shopping fails on the same friction every time: you know *what you're trying to do* ("dinner party tonight", "I'm out of coffee", "a guest is vegan"), but the app makes you translate that into individual product searches. Amazon Now removes that translation step.

The product is organized around two intelligence-first surfaces and a supporting commerce layer:

### 🔮 NowCast — the predictive home
The home screen doesn't lead with a search bar — it shows what you're about to need. NowCast fuses three live signals into ranked, explainable triggers you build with one tap:

- **Calendar** — an upcoming dinner party surfaces the exact ingredients for the headcount.
- **Smart-fridge** — items running low or out are flagged before you notice.
- **Purchase cadence** — recurring buys (coffee, milk, dishwasher tabs) are predicted from your real reorder rhythm.

Every line carries a human reason ("you reorder this every 9 days — last bought 9 days ago"), so the prediction is always explainable, never a black box.

### 🎙️ NowSpeak — the conversational agent
Describe the situation in plain language and the agent resolves it to a ready cart. NowSpeak handles four input modes through one interface, streamed token-by-token:

- **Natural language** — "a guest is vegan, what can I cook?" → a dietary-safe recipe + its full ingredient cart.
- **Pasted lists** — "milk, eggs, bread, coffee, 2 onions" → each item matched to a real product with quantities.
- **Recipe links** — drop a recipe URL → ingredients extracted and added.
- **Voice** — speak the request via the Web Speech API.

Allergy and dietary constraints (Aarav is allergic to nuts) are enforced across every resolution.

### 🛒 Commerce layer
- **Cook** — a recipe gallery with proportional serving-scaling; add every ingredient in one tap.
- **Group cart** — create a shared cart, invite family by link, and watch items combine live as each member joins (server-pushed in real time).
- **Smart checkout** — the best coupon for the current cart is evaluated and applied automatically; the customer can compare and switch offers.
- **Order history + one-tap reorder** — past orders refill the cart instantly.
- **Live order tracking** — ETA countdown and a moving rider on a staged tracker.

---

## Architecture

Amazon Now is a service-oriented application: a stateless API tier in front of an intelligence layer powered by **Amazon Bedrock**, with the storefront delivered as a mobile-first PWA.

```
┌──────────────────────────────────────────────────────────────┐
│  Storefront (PWA)            Next.js 16 · Tailwind v4          │
│  NowCast · NowSpeak · Cook · Group · Checkout · Tracking      │
└───────────────┬───────────────────────────┬──────────────────┘
                │ REST + Server-Sent Events  │
┌───────────────▼───────────────────────────▼──────────────────┐
│  API tier (FastAPI)                                            │
│  prediction · agent resolution · pricing · orders · groups    │
└──────┬───────────────────┬─────────────────────┬─────────────┘
       │                   │                     │
┌──────▼───────┐   ┌────────▼────────┐   ┌────────▼────────┐
│ Intelligence │   │  Catalog &      │   │  Signals        │
│ layer        │   │  pricing        │   │  store          │
│ (Bedrock)    │   │                 │   │                 │
└──────────────┘   └─────────────────┘   └─────────────────┘
```

### The intelligence layer on AWS

The NowSpeak agent and NowCast ranking run on the **Amazon Bedrock** model stack, which gives the product managed, secure, low-latency access to frontier LLMs without standing up inference infrastructure:

- **Amazon Bedrock** — hosts the foundation models behind NowSpeak (intent understanding, list/recipe parsing, dietary reasoning) and NowCast (signal fusion and reason generation). Model access is region-local and VPC-private.
- **Bedrock Knowledge Bases** — ground the agent in the live product catalog and recipe corpus so resolutions map to real, in-stock SKUs rather than invented items. Retrieval-augmented generation keeps answers catalog-accurate.
- **Bedrock Agents + Action Groups** — let the model call store functions (cart assembly, pricing, coupon evaluation, order placement) as tools, turning a natural-language request into concrete commerce actions.
- **Bedrock Guardrails** — enforce dietary and allergen safety (e.g. nut-allergy filtering) and keep responses on-policy.
- **Amazon Titan Embeddings** — power semantic matching from free-text items ("2 onions") to catalog products.

### Supporting AWS services

- **Amazon API Gateway + AWS Lambda / Amazon ECS Fargate** — host the FastAPI tier elastically.
- **Amazon DynamoDB** — fridge, history, calendar, profile, group-cart, and order state with single-digit-millisecond reads.
- **Amazon S3 + Amazon CloudFront** — serve product and recipe imagery from edge caches.
- **Amazon OpenSearch Service** — vector + keyword search over the catalog.
- **Amazon Personalize** — sharpens NowCast reorder-cadence predictions over time.
- **Amazon Cognito** — customer identity and group-cart invitations.
- **Amazon EventBridge + Amazon SNS** — order-lifecycle events and live tracking updates.
- **Amazon Bedrock streaming → SSE** — token-by-token NowSpeak replies and live group-cart fill delivered over Server-Sent Events.

---

## Running locally

The full stack runs on two processes.

```bash
# 1. API tier
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010

# 2. Storefront (new terminal)
cd frontend
pnpm install
pnpm exec next dev -p 3100
```

Open **http://localhost:3100** — best viewed in a narrow window; it renders as a phone.

### Catalog & content pipeline

```bash
uv run scripts/build_catalog.py   # hero products + imagery
uv run scripts/build_recipes.py   # recipe corpus + long-tail catalog
```

### Tests

```bash
cd backend  && uv run pytest -q              # API contract tests (21)
cd frontend && pnpm exec playwright test     # end-to-end flows + screenshots
```

---

## Project layout

```
amazonNow/
├── backend/          FastAPI API tier
│   ├── app/
│   │   ├── main.py       routes
│   │   ├── engine.py     prediction · agent resolution · pricing
│   │   ├── data.py       catalog, signals, profile
│   │   └── group.py      shared-cart engine
│   └── tests/
├── frontend/         Next.js 16 PWA
│   └── src/app/         NowCast · NowSpeak · Cook · Group · Checkout
├── config/           catalog, recipes, signals, pricing, personas
└── scripts/          catalog + recipe build pipeline
```

---

## Technologies used

**Cloud & AI (AWS)**
- Amazon Bedrock (foundation models)
- Amazon Bedrock Knowledge Bases
- Amazon Bedrock Agents & Action Groups
- Amazon Bedrock Guardrails
- Amazon Titan Embeddings
- Amazon API Gateway
- AWS Lambda / Amazon ECS Fargate
- Amazon DynamoDB
- Amazon S3 + Amazon CloudFront
- Amazon OpenSearch Service
- Amazon Personalize
- Amazon Cognito
- Amazon EventBridge + Amazon SNS

**Backend**
- Python 3.12
- FastAPI
- Uvicorn (ASGI)
- Server-Sent Events (SSE) streaming
- uv (packaging & environments)
- pytest + httpx (testing)

**Frontend**
- Next.js 16 (App Router)
- React 19
- TypeScript
- Tailwind CSS v4
- Framer Motion
- lucide-react
- Web Speech API
- Playwright (end-to-end testing)

**Tooling**
- pnpm
- ESLint
- Git
