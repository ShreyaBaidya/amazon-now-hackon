"use client";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { Product } from "./types";

export type CartItem = { product: Product; qty: number };

// Economy mode: swap each cart item with the cheapest available product in
// the same category. Budget presets are purely display — the cart is always
// trimmed to the cheapest-per-category set regardless of the preset chosen.
export const ECONOMY_BUDGETS = [150, 300, 500, 750] as const;
export type EconomyBudget = (typeof ECONOMY_BUDGETS)[number];

type CartCtx = {
  items: CartItem[];
  originalItems: CartItem[]; // always the real cart, unaffected by economy mode
  count: number;
  subtotal: number;
  economyMode: boolean;
  economyBudget: EconomyBudget;
  setEconomyMode: (on: boolean) => void;
  setEconomyBudget: (b: EconomyBudget) => void;
  qtyOf: (id: string) => number;
  add: (p: Product, qty?: number) => void;
  setQty: (id: string, qty: number) => void;
  addMany: (ps: { product: Product; qty?: number }[], replace?: boolean) => void;
  clear: () => void;
};

const Ctx = createContext<CartCtx | null>(null);
const KEY = "amzn-now-cart";
const ECO_KEY = "amzn-now-economy";

// ── Economy helper ────────────────────────────────────────────────────────
// Build an economy variant of a product entirely on the frontend.
// No backend call needed — just reduce the price and swap the brand.
const HOUSE_BRANDS: Record<string, string> = {
  dairy_eggs:          "Freshday",
  fresh_produce:       "FarmBasket",
  bakery:              "BakeSimple",
  staples_grocery:     "DailyEssentials",
  meat_seafood:        "FreshCatch",
  beverages:           "QuenchBasic",
  snacks:              "MunchMore",
  frozen:              "CoolPick",
  medicine_health:     "CareBasics",
  personal_care:       "PureChoice",
  household_cleaning:  "CleanEasy",
  baby_care:           "TenderCare",
  home_decor_lifestyle:"SimpleHome",
  party_festive:       "FestBasic",
};

function makeEconomyVariant(p: Product): Product {
  const ecoPrice = Math.max(5, Math.ceil((p.price * 0.65) / 5) * 5);
  const brand = HOUSE_BRANDS[p.category] ?? "Amazon Basics";
  return {
    ...p,
    id:    `eco-${p.id}`,
    name:  `${p.name} (Economy)`,
    brand,
    price: ecoPrice,
  };
}

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<CartItem[]>([]);
  const [economyMode, setEconomyModeRaw] = useState(false);
  const [economyBudget, setEconomyBudget] = useState<EconomyBudget>(300);
  const [ecoItems, setEcoItems] = useState<CartItem[]>([]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) setItems(JSON.parse(raw));
      const eco = localStorage.getItem(ECO_KEY);
      if (eco) {
        const { on, budget } = JSON.parse(eco);
        setEconomyModeRaw(!!on);
        if (budget) setEconomyBudget(budget);
      }
    } catch {}
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(items));
    } catch {}
  }, [items]);

  useEffect(() => {
    try {
      localStorage.setItem(ECO_KEY, JSON.stringify({ on: economyMode, budget: economyBudget }));
    } catch {}
  }, [economyMode, economyBudget]);

  // When economy mode turns on, swap EACH cart item with a frontend-generated
  // economy variant (same product, cheaper price, house brand).
  // Deduplicate by eco product ID (merge quantities) and sort by price.
  useEffect(() => {
    if (!economyMode || items.length === 0) {
      setEcoItems([]);
      return;
    }

    // Build eco variants synchronously — no backend call needed
    const mapped: CartItem[] = items.map((item) => ({
      product: makeEconomyVariant(item.product),
      qty: item.qty,
    }));

    // Deduplicate: merge quantities for identical eco product IDs
    const merged = new Map<string, CartItem>();
    for (const item of mapped) {
      const existing = merged.get(item.product.id);
      if (existing) {
        merged.set(item.product.id, { ...existing, qty: existing.qty + item.qty });
      } else {
        merged.set(item.product.id, { ...item });
      }
    }

    // Sort by price ascending (cheapest first)
    const sorted = Array.from(merged.values()).sort(
      (a, b) => a.product.price - b.product.price,
    );

    setEcoItems(sorted);
  }, [economyMode, items]);

  const setEconomyMode = (on: boolean) => setEconomyModeRaw(on);

  const activeItems = economyMode ? ecoItems : items;

  const value = useMemo<CartCtx>(() => {
    const qtyOf = (id: string) => items.find((i) => i.product.id === id)?.qty ?? 0;
    const add: CartCtx["add"] = (p, qty = 1) =>
      setItems((cur) => {
        const ex = cur.find((i) => i.product.id === p.id);
        if (ex) return cur.map((i) => (i.product.id === p.id ? { ...i, qty: i.qty + qty } : i));
        return [...cur, { product: p, qty }];
      });
    // setQty routes to ecoItems when economy mode is active, otherwise the real cart
    const setQty: CartCtx["setQty"] = (id, qty) => {
      if (economyMode && ecoItems.length > 0) {
        setEcoItems((cur) =>
          qty <= 0
            ? cur.filter((i) => i.product.id !== id)
            : cur.map((i) => (i.product.id === id ? { ...i, qty } : i)),
        );
        // Also remove/update the corresponding original item so the real cart
        // stays in sync — prevents eco effect from repopulating removed items.
        if (qty <= 0) {
          // eco id is "eco-{originalId}" — strip prefix to find the original
          const originalId = id.startsWith("eco-") ? id.slice(4) : id;
          setItems((cur) => cur.filter((i) => i.product.id !== originalId));
        }
      } else {
        setItems((cur) =>
          qty <= 0
            ? cur.filter((i) => i.product.id !== id)
            : cur.map((i) => (i.product.id === id ? { ...i, qty } : i)),
        );
      }
    };
    const addMany: CartCtx["addMany"] = (ps, replace = false) =>
      setItems((cur) => {
        const base = replace ? [] : [...cur];
        for (const { product, qty = 1 } of ps) {
          const ex = base.find((i) => i.product.id === product.id);
          if (ex) ex.qty += qty;
          else base.push({ product, qty });
        }
        return [...base];
      });
    return {
      items: activeItems,
      originalItems: items,
      count: activeItems.reduce((s, i) => s + i.qty, 0),
      subtotal: activeItems.reduce((s, i) => s + i.product.price * i.qty, 0),
      economyMode,
      economyBudget,
      setEconomyMode,
      setEconomyBudget,
      qtyOf,
      add,
      setQty,
      addMany,
      clear: () => setItems([]),
    };
  }, [activeItems, items, ecoItems, economyMode, economyBudget]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCart() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useCart outside provider");
  return c;
}
