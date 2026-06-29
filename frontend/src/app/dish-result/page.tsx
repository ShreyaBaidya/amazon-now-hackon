"use client";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronLeft, Clock, Minus, Plus, Users, AlertTriangle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import VegMark from "@/components/VegMark";
import { api } from "@/lib/api";
import { useCart } from "@/lib/cart";
import { rupee } from "@/lib/format";
import type { DishAnalysis, DishIngredient, Product, Recipe } from "@/lib/types";

// ─────────────────────────────────────────────────────────────────────────────
// Helper — only used for the AI-generated (non-stored) recipe path.
// For stored recipes the server rescales, so this is never called for them.
// ─────────────────────────────────────────────────────────────────────────────
function scaleDisplayQty(
  original: DishIngredient,
  baseQty: number | null,
  servings: number,
  baseServings: number,
): string {
  if (baseQty == null || baseQty === 0) {
    return original.display_qty || original.unit || "";
  }
  const factor = servings / Math.max(1, baseServings);
  const scaled = baseQty * factor;
  const rounded = scaled % 1 === 0 ? scaled : parseFloat(scaled.toFixed(2));
  const unit = original.unit || "";
  return unit ? `${rounded} ${unit}`.trim() : original.display_qty || `${rounded}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────
export default function DishResultPage() {
  const router = useRouter();
  const { addMany } = useCart();

  // Static analysis loaded once from sessionStorage
  const [analysis, setAnalysis] = useState<DishAnalysis | null>(null);
  const [heroImage, setHeroImage] = useState<string | null>(null);

  // Servings — shared by both paths
  const [servings, setServings] = useState(4);

  // ── Stored-recipe path: live Recipe fetched from the server on every servings change ──
  const [liveRecipe, setLiveRecipe] = useState<Recipe | null>(null);
  // Per-ingredient add-qty for the stored-recipe path (keyed by ingredient index)
  const [recipeQtyById, setRecipeQtyById] = useState<Record<string, number>>({});

  // ── AI-generated path: static ingredient list from the analysis snapshot ──
  const [lineQty, setLineQty] = useState<Record<string, number>>({});
  const [selected, setSelected] = useState<Record<string, boolean>>({});

  // ── Load from sessionStorage once ────────────────────────────────────────
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("dish-analysis");
      if (!raw) { router.replace("/recipes"); return; }
      const data: DishAnalysis = JSON.parse(raw);
      setAnalysis(data);
      setServings(data.base_servings || 4);

      const storedImage = sessionStorage.getItem("dish-image");
      if (storedImage) {
        setHeroImage(storedImage);
      } else if (data.image) {
        setHeroImage(data.image);
      }

      // AI-generated path initialisation
      if (!data.from_stored_recipe) {
        const initQty: Record<string, number> = {};
        const initSel: Record<string, boolean> = {};
        data.ingredients.forEach((ing, i) => {
          initQty[`ing-${i}`] = 1;
          initSel[`ing-${i}`] = ing.available;
        });
        setLineQty(initQty);
        setSelected(initSel);
      }
    } catch {
      router.replace("/recipes");
    }
  }, [router]);

  // ── Stored-recipe path: re-fetch from server whenever servings changes ───
  // This is exactly what /recipe/[id] does — reusing the same api.recipe() call.
  useEffect(() => {
    if (!analysis?.from_stored_recipe || !analysis.recipe_id) return;
    api.recipe(analysis.recipe_id, servings)
      .then((r) => {
        setLiveRecipe(r);
        // Reset per-ingredient add-qty to 1 for all available ingredients
        const initQty: Record<string, number> = {};
        r.ingredients.forEach((ing, i) => {
          if (ing.product) initQty[`r-${i}`] = 1;
        });
        setRecipeQtyById((prev) => {
          // Preserve existing user-set quantities; only initialise missing keys
          const merged = { ...initQty };
          Object.keys(prev).forEach((k) => { if (k in merged) merged[k] = prev[k]; });
          return merged;
        });
      })
      .catch(() => {});
  }, [analysis?.from_stored_recipe, analysis?.recipe_id, servings]);

  // ─── Stored-recipe helpers ────────────────────────────────────────────────
  const recipeQtyOf = (key: string) => recipeQtyById[key] ?? 1;
  const setRecipeLineQty = (key: string, qty: number) =>
    setRecipeQtyById((cur) => ({ ...cur, [key]: Math.max(0, Math.min(99, qty)) }));

  const recipeSelectedIngredients = useMemo(() => {
    if (!liveRecipe) return [];
    return liveRecipe.ingredients
      .filter((ing, i) => ing.product && recipeQtyOf(`r-${i}`) > 0)
      .map((ing, i) => ({ product: ing.product!, qty: recipeQtyOf(`r-${i}`), price: ing.price }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveRecipe, recipeQtyById]);

  const recipeSelectedCount = recipeSelectedIngredients.reduce((s, i) => s + i.qty, 0);
  const recipeSelectedTotal = recipeSelectedIngredients.reduce((s, i) => s + i.price * i.qty, 0);

  // ─── AI-generated helpers ─────────────────────────────────────────────────
  const qtyOf = (key: string) => lineQty[key] ?? 1;
  const isSelected = (key: string) => selected[key] ?? false;
  const setIng = (key: string, qty: number) =>
    setLineQty((cur) => ({ ...cur, [key]: Math.max(0, Math.min(99, qty)) }));
  const toggleSelect = (key: string) =>
    setSelected((cur) => ({ ...cur, [key]: !cur[key] }));

  const { selectedItems, totalCount, totalPrice } = useMemo(() => {
    if (!analysis || analysis.from_stored_recipe) {
      return { selectedItems: [], totalCount: 0, totalPrice: 0 };
    }
    const items: { product: Product; qty: number }[] = [];
    let count = 0;
    let price = 0;
    analysis.ingredients.forEach((ing, i) => {
      const key = `ing-${i}`;
      if (!ing.product || !isSelected(key)) return;
      const q = qtyOf(key);
      if (q <= 0) return;
      items.push({ product: ing.product, qty: q });
      count += q;
      price += ing.product.price * q;
    });
    return { selectedItems: items, totalCount: count, totalPrice: price };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysis, lineQty, selected]);

  // ─── Add to cart ──────────────────────────────────────────────────────────
  const addToCart = () => {
    if (analysis?.from_stored_recipe) {
      if (recipeSelectedCount === 0) return;
      addMany(recipeSelectedIngredients.map((i) => ({ product: i.product, qty: i.qty })));
    } else {
      if (selectedItems.length === 0) return;
      addMany(selectedItems);
    }
    router.push("/checkout?src=dish");
  };

  const ctaCount = analysis?.from_stored_recipe ? recipeSelectedCount : totalCount;
  const ctaTotal = analysis?.from_stored_recipe ? recipeSelectedTotal : totalPrice;

  // ─── Loading state ────────────────────────────────────────────────────────
  if (!analysis) {
    return <div className="flex-1 grid place-items-center text-ink2">Loading…</div>;
  }
  // For stored recipes, wait for the first live fetch
  if (analysis.from_stored_recipe && !liveRecipe) {
    return <div className="flex-1 grid place-items-center text-ink2">Loading…</div>;
  }

  // ─── Shared header values ─────────────────────────────────────────────────
  const dishName = liveRecipe?.name ?? analysis.dish_name;
  const cuisine = liveRecipe?.cuisine ?? analysis.cuisine;
  const cookTime = liveRecipe?.time_min ?? analysis.cooking_time_min;
  const ingredientCount = liveRecipe?.ingredient_count ?? analysis.ingredient_count;

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto no-scrollbar pb-40">

        {/* Hero image */}
        <div className="relative h-44">
          {heroImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={heroImage}
              alt={dishName}
              className="absolute inset-0 h-full w-full object-cover"
              onError={() => setHeroImage(null)}
            />
          ) : (
            <div className="absolute inset-0 bg-gradient-to-b from-amzn-dark to-amzn-blue2" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-black/30" />
          <button
            onClick={() => router.back()}
            className="absolute top-3 left-3 h-9 w-9 rounded-full bg-black/40 text-white grid place-items-center z-10"
          >
            <ChevronLeft size={20} />
          </button>
          <div className="absolute bottom-3 left-4 right-4 text-white">
            <p className="text-[22px] font-extrabold leading-tight">{dishName}</p>
            <p className="text-[12px] flex items-center gap-2 mt-0.5">
              <span className="flex items-center gap-1">
                <Clock size={12} /> {cookTime} min
              </span>
              · {cuisine}
              · {ingredientCount} ingredients
            </p>
          </div>
        </div>

        {/* Servings control */}
        <div className="bg-white mx-3 mt-3 rounded-2xl border border-line p-3 flex items-center justify-between">
          <span className="flex items-center gap-2 text-[14px] font-semibold">
            <Users size={18} className="text-amzn-orange" /> Servings
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setServings((s) => Math.max(1, s - 1))}
              className="h-8 w-8 rounded-lg bg-paper grid place-items-center text-amzn-green"
              aria-label="Decrease servings"
            >
              <Minus size={16} />
            </button>
            <motion.span
              key={servings}
              initial={{ scale: 0.7 }}
              animate={{ scale: 1 }}
              className="w-6 text-center text-[17px] font-bold"
            >
              {servings}
            </motion.span>
            <button
              onClick={() => setServings((s) => Math.min(12, s + 1))}
              className="h-8 w-8 rounded-lg bg-paper grid place-items-center text-amzn-green"
              aria-label="Increase servings"
            >
              <Plus size={16} />
            </button>
          </div>
        </div>

        {/* Ingredient list */}
        <div className="bg-white mx-3 mt-3 rounded-2xl border border-line px-3">
          <p className="text-[13px] font-bold pt-3 pb-1">
            Ingredients · scaled for {servings}
          </p>
          <div className="divide-y divide-line/70">

            {/* ── Stored-recipe path: render from live Recipe (same as Cook page) ── */}
            {analysis.from_stored_recipe && liveRecipe && liveRecipe.ingredients.map((ing, i) => {
              const key = `r-${i}`;
              const id = ing.product?.id ?? `ingredient-${i}`;
              const qty = ing.product ? recipeQtyOf(key) : 0;
              const off = ing.product ? qty <= 0 : false;
              return (
                <div key={key} className="flex items-center gap-2.5 py-2.5">
                  {ing.product && (
                    <button
                      onClick={() => setRecipeLineQty(key, off ? 1 : 0)}
                      className={`h-5 w-5 rounded-md border-2 grid place-items-center shrink-0 ${
                        off ? "border-line bg-white" : "border-amzn-green bg-amzn-green"
                      }`}
                      aria-label={off ? `select ${ing.name}` : `deselect ${ing.name}`}
                    >
                      {!off && <Check size={13} className="text-white" strokeWidth={3} />}
                    </button>
                  )}
                  <div className={`h-11 w-11 rounded-lg bg-paper grid place-items-center overflow-hidden shrink-0 ${off ? "opacity-40" : ""}`}>
                    {ing.product?.image ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={ing.product.image} alt="" className="h-[85%] w-[85%] object-contain" />
                    ) : null}
                  </div>
                  <div className={`flex-1 min-w-0 ${off ? "opacity-40" : ""}`}>
                    <div className="flex items-center gap-1">
                      {ing.product && <VegMark product={ing.product} size={12} />}
                      <p className="text-[13px] font-semibold truncate">{ing.name}</p>
                    </div>
                    <p className="text-[11px] text-ink2">{ing.display_qty}</p>
                  </div>
                  <div className={`shrink-0 flex flex-col items-end gap-1 ${off ? "opacity-50" : ""}`}>
                    <span className={`text-[12px] font-bold ${off ? "line-through" : ""}`}>
                      {rupee(ing.price * Math.max(0, qty || 1))}
                    </span>
                    {ing.product && (
                      <div className="h-7 w-[78px] rounded-lg bg-amzn-green text-white text-[12px] font-bold flex items-center justify-between px-1">
                        <button
                          onClick={() => setRecipeLineQty(key, qty - 1)}
                          className="grid place-items-center h-full w-6"
                          aria-label={`decrease ${ing.name}`}
                        >-</button>
                        <motion.span key={qty} initial={{ scale: 0.75 }} animate={{ scale: 1 }}>
                          {qty}
                        </motion.span>
                        <button
                          onClick={() => setRecipeLineQty(key, qty + 1)}
                          className="grid place-items-center h-full w-6"
                          aria-label={`increase ${ing.name}`}
                        >+</button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* ── AI-generated path: render from static analysis snapshot ── */}
            {!analysis.from_stored_recipe && analysis.ingredients.map((ing, i) => {
              const key = `ing-${i}`;
              const qty = qtyOf(key);
              const sel = isSelected(key);
              const dimmed = !sel;
              const scaledLabel = scaleDisplayQty(ing, ing.qty, servings, analysis.base_servings);
              return (
                <div key={key} className="flex items-center gap-2.5 py-2.5">
                  {ing.available ? (
                    <button
                      onClick={() => toggleSelect(key)}
                      className={`h-5 w-5 rounded-md border-2 grid place-items-center shrink-0 transition ${
                        sel ? "border-amzn-green bg-amzn-green" : "border-line bg-white"
                      }`}
                      aria-label={sel ? `deselect ${ing.name}` : `select ${ing.name}`}
                    >
                      {sel && <Check size={13} className="text-white" strokeWidth={3} />}
                    </button>
                  ) : (
                    <span className="h-5 w-5 shrink-0" />
                  )}
                  <div className={`h-11 w-11 rounded-lg bg-paper grid place-items-center overflow-hidden shrink-0 ${dimmed ? "opacity-40" : ""}`}>
                    {ing.product?.image ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={ing.product.image} alt="" className="h-[85%] w-[85%] object-contain" />
                    ) : (
                      <span className="text-[9px] text-ink2 font-semibold text-center px-1 leading-tight">N/A</span>
                    )}
                  </div>
                  <div className={`flex-1 min-w-0 ${dimmed ? "opacity-40" : ""}`}>
                    <div className="flex items-center gap-1">
                      {ing.product && <VegMark product={ing.product} size={12} />}
                      <p className="text-[13px] font-semibold truncate">
                        {ing.product?.name ?? ing.name}
                      </p>
                    </div>
                    <p className="text-[11px] text-ink2">{scaledLabel}</p>
                    {!ing.available && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] text-ink2 font-semibold mt-0.5">
                        <AlertTriangle size={10} className="text-amzn-orange" /> Unavailable
                      </span>
                    )}
                  </div>
                  <div className={`shrink-0 flex flex-col items-end gap-1 ${dimmed ? "opacity-50" : ""}`}>
                    <span className={`text-[12px] font-bold ${!sel && ing.available ? "line-through" : ""}`}>
                      {ing.product ? rupee(ing.product.price * Math.max(1, qty)) : "—"}
                    </span>
                    {ing.available && (
                      <div className="h-7 w-[78px] rounded-lg bg-amzn-green text-white text-[12px] font-bold flex items-center justify-between px-1">
                        <button onClick={() => setIng(key, qty - 1)} className="grid place-items-center h-full w-6" aria-label={`decrease ${ing.name}`}>-</button>
                        <motion.span key={qty} initial={{ scale: 0.75 }} animate={{ scale: 1 }}>{qty}</motion.span>
                        <button onClick={() => setIng(key, qty + 1)} className="grid place-items-center h-full w-6" aria-label={`increase ${ing.name}`}>+</button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

          </div>
        </div>
      </div>

      {/* Sticky bottom CTA */}
      <div className="absolute bottom-16 inset-x-0 z-20 bg-white border-t border-line p-3">
        <button
          onClick={addToCart}
          disabled={ctaCount === 0}
          className="w-full rounded-2xl bg-amzn-yellow2 text-amzn-dark font-bold py-3.5
                     flex items-center justify-center gap-2 disabled:opacity-50"
        >
          Add {ctaCount} item{ctaCount !== 1 ? "s" : ""} · {rupee(ctaTotal)}
        </button>
      </div>
    </div>
  );
}
