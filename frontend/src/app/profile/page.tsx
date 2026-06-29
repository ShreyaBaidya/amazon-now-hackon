"use client";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  Leaf,
  MapPin,
  Package,
  Wallet,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Profile } from "@/lib/types";

export default function ProfilePage() {
  const router = useRouter();
  const [p, setP] = useState<Profile | null>(null);
  const [prefs, setPrefs] = useState<string[]>([]);
  const [allergens, setAllergens] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.profile().then((d) => {
      setP(d);
      setPrefs(d.dietary.preferences || []);
      setAllergens(d.dietary.allergens || []);
    });
  }, []);

  const toggle = (list: string[], set: (v: string[]) => void, v: string) => {
    set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
    setSaved(false);
  };

  const save = async () => {
    await api.updateDietary({ preferences: prefs, allergens, exclude_keywords: [] });
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  if (!p) return <div className="flex-1 grid place-items-center text-ink2">Loading…</div>;

  return (
    <div className="flex flex-col h-full">
      <header className="bg-amzn-dark text-white px-3 pt-2 pb-3 shrink-0 flex items-center gap-2">
        <button onClick={() => router.push("/")} className="p-1">
          <ChevronLeft size={22} />
        </button>
        <span className="font-bold">Your profile</span>
      </header>

      <main className="flex-1 overflow-y-auto no-scrollbar p-3 pb-28">
        {/* identity */}
        <div className="bg-white rounded-2xl border border-line shadow-card p-4 flex items-center gap-3">
          <div className="h-14 w-14 rounded-full grid place-items-center text-xl font-bold text-amzn-dark" style={{ background: p.avatar_color }}>
            {p.first_name[0]}
          </div>
          <div>
            <p className="font-bold text-[16px]">{p.name}</p>
            {p.household && <p className="text-[12px] text-ink2">{p.household}</p>}
          </div>
        </div>

        {/* address + payment */}
        <div className="bg-white rounded-2xl border border-line shadow-card mt-3 divide-y divide-line">
          <Row icon={<MapPin size={17} className="text-amzn-orange" />} title={`Deliver to ${p.address.label ?? "Home"}`} sub={`${p.address.line1}, ${p.address.line2}`} />
          <Row icon={<Wallet size={17} className="text-amzn-orange" />} title={p.payment.label} sub={p.payment.masked} />
          <button onClick={() => router.push("/orders")} className="w-full">
            <Row icon={<Package size={17} className="text-amzn-orange" />} title="Your orders" sub="Track & reorder in one tap" chevron />
          </button>
        </div>

        {/* dietary preferences */}
        <div className="bg-white rounded-2xl border border-line shadow-card mt-3 p-4">
          <p className="font-bold text-[15px] flex items-center gap-1.5">
            <Leaf size={16} className="text-amzn-green" /> Dietary preferences
          </p>
          <p className="text-[12px] text-ink2 mt-0.5">We filter and flag products across the app to match.</p>
          <div className="flex flex-wrap gap-2 mt-3">
            {p.diet_options.map((o) => (
              <Chip key={o} active={prefs.includes(o)} onClick={() => toggle(prefs, setPrefs, o)}>
                {o}
              </Chip>
            ))}
          </div>
        </div>

        {/* allergens */}
        <div className="bg-white rounded-2xl border border-line shadow-card mt-3 mb-8 p-4">
          <p className="font-bold text-[15px] flex items-center gap-1.5">
            <AlertTriangle size={16} className="text-amzn-red" /> Allergies to flag
          </p>
          <p className="text-[12px] text-ink2 mt-0.5">Anything containing these gets a clear warning badge.</p>
          <div className="flex flex-wrap gap-2 mt-3">
            {p.allergen_options.map((o) => (
              <Chip key={o} active={allergens.includes(o)} onClick={() => toggle(allergens, setAllergens, o)} danger>
                {o}
              </Chip>
            ))}
          </div>
        </div>
      </main>

      <div className="absolute bottom-16 inset-x-0 z-20 bg-white border-t border-line p-3">
        <button
          onClick={save}
          className={`w-full rounded-2xl font-bold py-3.5 flex items-center justify-center gap-2 transition ${
            saved ? "bg-amzn-green text-white" : "bg-amzn-yellow2 text-amzn-dark"
          }`}
        >
          {saved ? (
            <>
              <Check size={18} /> Saved — applied everywhere
            </>
          ) : (
            "Save preferences"
          )}
        </button>
      </div>
    </div>
  );
}

function Row({ icon, title, sub, chevron }: { icon: React.ReactNode; title: string; sub: string; chevron?: boolean }) {
  return (
    <div className="flex items-center gap-3 p-3.5 text-left">
      {icon}
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-semibold leading-tight">{title}</p>
        <p className="text-[11px] text-ink2 truncate">{sub}</p>
      </div>
      {chevron && <span className="text-ink2">›</span>}
    </div>
  );
}

function Chip({
  active,
  onClick,
  danger,
  children,
}: {
  active: boolean;
  onClick: () => void;
  danger?: boolean;
  children: React.ReactNode;
}) {
  const on = danger ? "bg-amzn-red text-white border-amzn-red" : "bg-amzn-green text-white border-amzn-green";
  return (
    <motion.button
      whileTap={{ scale: 0.94 }}
      onClick={onClick}
      className={`text-[12px] font-semibold px-3 py-1.5 rounded-full border capitalize flex items-center gap-1 ${
        active ? on : "bg-white text-ink2 border-line"
      }`}
    >
      {active && <Check size={12} />}
      {children}
    </motion.button>
  );
}
