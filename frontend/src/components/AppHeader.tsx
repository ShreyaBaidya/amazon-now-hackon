"use client";
import { ChevronDown, MapPin, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useBoot } from "@/lib/boot";

export default function AppHeader({ greeting }: { greeting?: string }) {
  const boot = useBoot();
  const router = useRouter();
  return (
    <header className="bg-amzn-dark text-white px-4 pt-2 pb-1 shrink-0">
      <div className="flex items-center justify-between">
        <button className="flex items-start gap-1.5 text-left">
          <MapPin size={18} className="text-amzn-orange mt-0.5" />
          <span className="leading-tight">
            <span className="flex items-center gap-1 text-[11px] text-white/70">
              Delivery in <b className="text-amzn-yellow">{boot?.settings.eta_default_min ?? 14} min</b>
            </span>
            <span className="flex items-center gap-1 text-[12px] font-semibold">
              {boot?.settings.delivery_zone ?? "Koramangala, Bengaluru"}
              <ChevronDown size={14} />
            </span>
          </span>
        </button>
        <button
          onClick={() => router.push("/profile")}
          aria-label="Your profile"
          className="h-8 w-8 rounded-full grid place-items-center text-sm font-bold text-amzn-dark active:scale-95 transition"
          style={{ background: boot?.user.avatar_color ?? "#FF9900" }}
        >
          {boot?.user.first_name?.[0] ?? "A"}
        </button>
      </div>

      <button
        onClick={() => router.push("/search")}
        className="mt-2 w-full h-8 rounded-xl bg-white text-ink2 flex items-center gap-2 px-3 text-sm"
      >
        <Search size={15} />
        <span>Search Amazon Now</span>
      </button>
      {greeting && <p className="mt-1 text-[12px] text-white/80">{greeting}</p>}
    </header>
  );
}
