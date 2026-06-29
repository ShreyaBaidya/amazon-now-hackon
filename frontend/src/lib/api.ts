import type {
  Bootstrap,
  CouponEval,
  DishAnalysis,
  GroupCart,
  NowCast,
  Dietary,
  Order,
  PastOrder,
  Product,
  Profile,
  Recipe,
  RecipeSummary,
  SpeakResult,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8010";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

export const api = {
  base: BASE,
  bootstrap: () => get<Bootstrap>("/api/bootstrap"),
  profile: () => get<Profile>("/api/profile"),
  updateDietary: (d: { preferences: string[]; allergens: string[]; exclude_keywords: string[] }) =>
    fetch(`${BASE}/api/profile/dietary`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(d),
    }).then((r) => r.json() as Promise<Dietary>),
  nowcast: () => get<NowCast>("/api/nowcast"),
  catalog: (q = "", category = "", limit = 40) =>
    get<{ products: Product[] }>(
      `/api/catalog?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}&limit=${limit}`,
    ),
  recipes: () => get<{ recipes: RecipeSummary[] }>("/api/recipes"),
  recipe: (id: string, servings: number) =>
    get<Recipe>(`/api/recipe/${id}?servings=${servings}`),
  speakStarters: () => get<{ chips: string[] }>("/api/nowspeak/starters"),
  speak: (q: string) => get<SpeakResult>(`/api/nowspeak?q=${encodeURIComponent(q)}`),
  coupons: (items: { product_id: string; qty: number }[], payment = "upi") =>
    fetch(`${BASE}/api/coupons`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, payment }),
    }).then((r) => r.json() as Promise<CouponEval>),
  order: (items: { product_id: string; qty: number }[], eta_min?: number, coupon_code?: string) =>
    fetch(`${BASE}/api/order`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, eta_min, coupon_code }),
    }).then((r) => r.json() as Promise<Order>),
  getOrder: (id: string) => get<Order>(`/api/order/${id}`),
  orders: () => get<{ orders: PastOrder[] }>("/api/orders"),
  streamUrl: (q: string) => `${BASE}/api/nowspeak/stream?q=${encodeURIComponent(q)}`,

  groupCreate: (items: { product_id: string; qty: number }[]) =>
    fetch(`${BASE}/api/group/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    }).then((r) => r.json() as Promise<GroupCart>),
  groupGet: (id: string) => get<GroupCart>(`/api/group/${id}`),
  groupJoin: (id: string, name: string) =>
    fetch(`${BASE}/api/group/${id}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then((r) => r.json() as Promise<GroupCart>),
  groupAdd: (id: string, product_id: string, qty: number, added_by: string) =>
    fetch(`${BASE}/api/group/${id}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id, qty, added_by }),
    }).then((r) => r.json() as Promise<GroupCart>),
  groupStreamUrl: (id: string, play = false) =>
    `${BASE}/api/group/${id}/stream${play ? "?play=1" : ""}`,
  groupCheckout: (id: string) =>
    fetch(`${BASE}/api/group/${id}/checkout`, { method: "POST" })
      .then((r) => r.json() as Promise<{ ok: boolean }>),

  analyzeDish: (imageFile: File): Promise<DishAnalysis> => {
    const form = new FormData();
    form.append("image", imageFile);
    return fetch(`${BASE}/api/dish/analyze`, { method: "POST", body: form }).then((r) => {
      if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.detail || r.statusText)));
      return r.json() as Promise<DishAnalysis>;
    });
  },
};

export const img = (path: string) => (path ? `${path}` : "");
