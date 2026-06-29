"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import AppHeader from "@/components/AppHeader";
import NowCast from "@/components/NowCast";
import { ProductCard } from "@/components/ProductCard";
import { api } from "@/lib/api";
import { useBoot } from "@/lib/boot";
import type { Product } from "@/lib/types";

export default function HomePage() {
  const boot = useBoot();
  const router = useRouter();
  const [trending, setTrending] = useState<Product[]>([]);

  useEffect(() => {
    api.catalog("", "snacks", 8).then((d) => setTrending(d.products)).catch(() => {});
  }, []);

  return (
    <div className="flex flex-col h-full">
      <AppHeader greeting={boot ? `${boot.settings.demo_now_label} · Hi ${boot.user.first_name} 👋` : undefined} />
      <main className="flex-1 overflow-y-auto no-scrollbar pb-25 pt-2">
        <NowCast />

        {/* categories */}
        <section className="px-4 mt-6">
          <h2 className="text-[15px] font-bold mb-2">Shop by category</h2>
          <div className="grid grid-cols-4 gap-2">
            {(boot?.categories ?? []).map((c) => (
              <button
                key={c.id}
                onClick={() => router.push(`/search?category=${c.id}`)}
                className="bg-white rounded-2xl border border-line p-2 flex flex-col items-center gap-1 shadow-card active:scale-95 transition"
              >
                <span className="text-2xl">{c.emoji}</span>
                <span className="text-[10px] font-medium text-center leading-tight">{c.label}</span>
              </button>
            ))}
          </div>
        </section>

        {/* cook banner */}
        <section className="px-4 mt-5">
          <button
            onClick={() => router.push("/recipes")}
            className="w-full rounded-2xl bg-gradient-to-r from-amzn-green to-emerald-700 text-white p-3.5 flex items-center justify-between text-left active:scale-[0.99] transition"
          >
            <div>
              <p className="font-bold text-[15px]">Cooking tonight? 🍳</p>
              <p className="text-[12px] text-white/80">Pick a dish — we add every ingredient, scaled</p>
            </div>
            <span className="text-2xl">→</span>
          </button>
        </section>

        {/* group cart banner */}
        <section className="px-4 mt-3">
          <button
            onClick={() => router.push("/group")}
            className="w-full rounded-2xl bg-gradient-to-r from-amzn-purple to-indigo-700 text-white p-3.5 flex items-center justify-between text-left active:scale-[0.99] transition "
          >
            <div>
              <p className="font-bold text-[15px]">Shop together 👨‍👩‍👧</p>
              <p className="text-[12px] text-white/80">One family cart — everyone adds, one delivery</p>
            </div>
            <span className="text-2xl">→</span>
          </button>
        </section>

        {/* trending */}
        <section className="mt-6">
          <h2 className="text-[15px] font-bold mb-2 px-4">Snacks for tonight 🍿</h2>
          <div className="flex gap-2.5 overflow-x-auto no-scrollbar px-4 pb-1">
            {trending.map((p) => (
              <div key={p.id} className="w-[140px] shrink-0">
                <ProductCard product={p} />
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
