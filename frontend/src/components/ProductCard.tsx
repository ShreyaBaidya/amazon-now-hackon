"use client";
import { Star } from "lucide-react";
import { useCart } from "@/lib/cart";
import { rupee } from "@/lib/format";
import type { Product } from "@/lib/types";
import Stepper from "./Stepper";
import VegMark, { AllergenBadge, DietaryTags } from "./VegMark";

export function ProductCard({ product }: { product: Product }) {
  const { qtyOf, add, setQty } = useCart();
  const qty = qtyOf(product.id);
  return (
    <div className={`w-full bg-white rounded-2xl border p-2.5 flex flex-col shadow-card ${product.allergen_conflict ? "border-amzn-red/40" : "border-line"}`}>
      <div className="relative aspect-square rounded-xl bg-paper overflow-hidden grid place-items-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={product.image} alt={product.name} className="h-[82%] w-[82%] object-contain" loading="lazy" />
        {product.allergen_conflict && (
          <span className="absolute top-1.5 left-1.5 bg-amzn-red text-white text-[9px] font-bold px-1.5 py-0.5 rounded-md">
            ⚠ {product.warnings?.[0]}
          </span>
        )}
      </div>
      <div className="flex items-center gap-1 mt-2">
        <VegMark product={product} />
        <span className="text-[10px] text-ink2 truncate">{product.brand}</span>
      </div>
      <p className="text-[13px] font-semibold leading-tight line-clamp-2 min-h-[34px] mt-0.5">
        {product.name}
      </p>
      <div className="flex items-center gap-1 text-[10px] text-ink2 mt-0.5">
        <span className="flex items-center gap-0.5 bg-amzn-green text-white px-1 rounded">
          {product.rating.toFixed(1)} <Star size={8} fill="white" />
        </span>
        <span>{product.size}</span>
      </div>
      {/* Extra dietary tags (GF, Keto, Halal) */}
      <div className="mt-1">
        <DietaryTags product={product} />
      </div>
      <div className="flex items-center justify-between mt-2">
        <span className="text-sm font-bold">{rupee(product.price)}</span>
        <Stepper
          qty={qty}
          size="sm"
          onAdd={() => add(product)}
          onInc={() => setQty(product.id, qty + 1)}
          onDec={() => setQty(product.id, qty - 1)}
        />
      </div>
    </div>
  );
}

export function ProductRow({
  product,
  qty,
  reason,
  badge,
}: {
  product: Product;
  qty?: number;
  reason?: string;
  badge?: React.ReactNode;
}) {
  const { qtyOf, add, setQty } = useCart();
  const q = qtyOf(product.id);
  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className="h-14 w-14 rounded-xl bg-paper grid place-items-center shrink-0 overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={product.image} alt={product.name} className="h-[84%] w-[84%] object-contain" loading="lazy" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1">
          <VegMark product={product} size={12} />
          <p className="text-[13px] font-semibold leading-tight truncate">{product.name}</p>
        </div>
        <p className="text-[11px] text-ink2">
          {product.size}
          {qty && qty > 1 ? ` · ×${qty}` : ""}
        </p>
        {reason && <p className="text-[11px] text-ink2 mt-0.5 truncate">{reason}</p>}
        {badge}
        <DietaryTags product={product} />
        <AllergenBadge product={product} />
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
        <span className="text-sm font-bold">{rupee(product.price)}</span>
        <Stepper
          qty={q}
          size="sm"
          onAdd={() => add(product)}
          onInc={() => setQty(product.id, q + 1)}
          onDec={() => setQty(product.id, q - 1)}
        />
      </div>
    </div>
  );
}
