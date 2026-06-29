"use client";
import { Camera, ChevronLeft, Clock } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import DishUploadModal from "@/components/DishUploadModal";
import { api } from "@/lib/api";
import type { RecipeSummary } from "@/lib/types";

export default function RecipesPage() {
  const router = useRouter();
  const [recipes, setRecipes] = useState<RecipeSummary[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  useEffect(() => {
    api.recipes().then((d) => setRecipes(d.recipes)).catch(() => {});
  }, []);

  return (
    <div className="flex flex-col h-full">
      <header className="bg-amzn-dark text-white px-3 pt-2 pb-3 shrink-0 flex items-center gap-2">
        <button onClick={() => router.push("/")} className="p-1">
          <ChevronLeft size={22} />
        </button>
        <div className="flex-1">
          <p className="font-bold">Cook something tonight</p>
          <p className="text-[11px] text-white/60">Pick a dish — we&apos;ll add every ingredient</p>
        </div>
        {/* Camera / Upload icon — opens the AI dish recognition modal */}
        <button
          onClick={() => setModalOpen(true)}
          aria-label="Identify dish from photo"
          className="h-9 w-9 rounded-full bg-white/10 grid place-items-center text-white active:scale-95 transition"
        >
          <Camera size={20} />
        </button>
      </header>
      <main className="flex-1 overflow-y-auto no-scrollbar p-3 pb-28">
        <div className="grid grid-cols-2 gap-2.5">
          {recipes.map((r) => (
            <Link
              key={r.id}
              href={`/recipe/${r.id}`}
              className="bg-white rounded-2xl border border-line overflow-hidden shadow-card active:scale-[0.98] transition"
            >
              <div className="relative h-28">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={r.image} alt={r.name} className="h-full w-full object-cover" loading="lazy" />
                <span className="absolute top-1.5 right-1.5 bg-white/90 rounded-full px-1.5 py-0.5 text-[10px] font-semibold flex items-center gap-0.5">
                  <Clock size={9} /> {r.time_min}m
                </span>
              </div>
              <div className="p-2">
                <p className="text-[13px] font-bold leading-tight line-clamp-1">{r.name}</p>
                <p className="text-[11px] text-ink2">
                  {r.cuisine} · {r.ingredient_count} items
                </p>
                <div className="flex gap-1 mt-1">
                  {r.dietary_tags.slice(0, 2).map((t) => (
                    <span key={t} className="text-[9px] font-semibold bg-amzn-greenlite text-amzn-green px-1.5 py-0.5 rounded-full capitalize">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            </Link>
          ))}
        </div>
      </main>

      <DishUploadModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  );
}
