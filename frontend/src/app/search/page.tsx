"use client";
import { ChevronLeft, Search, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ProductCard } from "@/components/ProductCard";
import { api } from "@/lib/api";
import { useBoot } from "@/lib/boot";
import type { Product } from "@/lib/types";

function SearchInner() {
  const router = useRouter();
  const params = useSearchParams();
  const boot = useBoot();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [cat, setCat] = useState(params.get("category") ?? "");
  const [products, setProducts] = useState<Product[]>([]);
  const [showExcluded, setShowExcluded] = useState(false);

  // Does the user have a dietary preference that filters products?
  const hasDietFilter = (boot?.user.dietary.preferences?.length ?? 0) > 0;
  const dietLabel = boot?.user.dietary.preferences_label ?? "";

  useEffect(() => {
    const t = setTimeout(() => {
      // showExcluded is always true to get all products
      api.catalog(q, cat, 1000, true)
        .then((d) => setProducts(d.products))
        .catch(() => {});
    }, 180);
    return () => clearTimeout(t);
  }, [q, cat]);

  const catLabel = useMemo(
    () => boot?.categories.find((c) => c.id === cat)?.label,
    [boot, cat],
  );

  return (
    <div className="flex flex-col h-full">
      <header className="bg-amzn-dark text-white px-3 pt-2 pb-3 shrink-0">
        <div className="flex items-center gap-2">
          <button onClick={() => router.push("/")} className="p-1">
            <ChevronLeft size={22} />
          </button>
          <div className="flex-1 flex items-center bg-white text-ink rounded-xl px-3 h-10">
            <Search size={17} className="text-ink2" />
            <input
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search milk, snacks, medicine…"
              className="flex-1 bg-transparent outline-none text-[13px] ml-2"
            />
            {q && (
              <button onClick={() => setQ("")}>
                <X size={16} className="text-ink2" />
              </button>
            )}
          </div>
        </div>
        <div className="flex gap-1.5 overflow-x-auto no-scrollbar mt-2.5">
          <Chip active={!cat} onClick={() => setCat("")}>
            All
          </Chip>
          {(boot?.categories ?? []).map((c) => (
            <Chip key={c.id} active={cat === c.id} onClick={() => setCat(c.id)}>
              {c.emoji} {c.label}
            </Chip>
          ))}
        </div>
      </header>

      <main className="flex-1 overflow-y-auto no-scrollbar pb-28">
        {/* Diet filter bar — changed to indicator only */}


        <div className="p-3">
          <p className="text-[12px] text-ink2 mb-2">
            {catLabel ? catLabel : q ? `Results for "${q}"` : "Popular right now"} · {products.length} items
          </p>
          <div className="grid grid-cols-2 gap-2.5">
            {products.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`shrink-0 text-[12px] font-medium px-3 py-1.5 rounded-full whitespace-nowrap ${
        active ? "bg-amzn-yellow2 text-amzn-dark" : "bg-white/10 text-white"
      }`}
    >
      {children}
    </button>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="flex-1 grid place-items-center text-ink2">Loading…</div>}>
      <SearchInner />
    </Suspense>
  );
}
