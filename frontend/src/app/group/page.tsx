"use client";
import { ChevronLeft, LogIn, Users, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useBoot } from "@/lib/boot";
import { useCart } from "@/lib/cart";
import { rupee } from "@/lib/format";

const ACTIVE_KEY = "amzn-now-active-group";

type ActiveGroup = { gid: string; name: string; host: boolean };

function getActive(): ActiveGroup | null {
  try {
    const raw = localStorage.getItem(ACTIVE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveActive(g: ActiveGroup) {
  try {
    localStorage.setItem(ACTIVE_KEY, JSON.stringify(g));
  } catch {}
}

function clearActive() {
  try {
    localStorage.removeItem(ACTIVE_KEY);
  } catch {}
}

function GroupEntry() {
  const router = useRouter();
  const boot = useBoot();
  const { items, subtotal } = useCart();
  const prefillCode = useSearchParams().get("code") || "";
  const [code, setCode] = useState(prefillCode);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [active, setActive] = useState<ActiveGroup | null>(null);
  const [activeValid, setActiveValid] = useState(true);

  // check for an active group membership on mount
  useEffect(() => {
    const saved = getActive();
    if (!saved) return;
    // verify the group still exists on the backend
    api.groupGet(saved.gid)
      .then((cart) => {
        if ((cart as { id?: string }).id) {
          setActive(saved);
          setActiveValid(true);
        } else {
          clearActive();
          setActiveValid(false);
        }
      })
      .catch(() => {
        clearActive();
        setActiveValid(false);
      });
  }, []);

  const create = async () => {
    setBusy(true);
    const cart = await api.groupCreate(items.map((i) => ({ product_id: i.product.id, qty: i.qty })));
    saveActive({ gid: cart.id, name: boot?.user.first_name || "You", host: true });
    router.push(`/group/${cart.id}?host=1`);
  };

  const join = async () => {
    if (!code.trim() || !name.trim()) return;
    setBusy(true);
    setErr("");
    const cart = await api.groupJoin(code.trim().toUpperCase(), name.trim());
    if ((cart as { id?: string }).id) {
      saveActive({ gid: code.trim().toUpperCase(), name: name.trim(), host: false });
      router.push(`/group/${code.trim().toUpperCase()}?me=${encodeURIComponent(name.trim())}`);
    } else {
      setErr("No cart with that code");
      setBusy(false);
    }
  };

  const leave = () => {
    clearActive();
    setActive(null);
  };

  return (
    <div className="flex flex-col h-full">
      <header className="bg-amzn-dark text-white px-3 pt-2 pb-3 shrink-0 flex items-center gap-2">
        <button onClick={() => router.push("/")} className="p-1">
          <ChevronLeft size={22} />
        </button>
        <span className="font-bold flex items-center gap-1.5">
          <Users size={16} className="text-amzn-yellow" /> Shop together
        </span>
      </header>

      <main className="flex-1 overflow-y-auto no-scrollbar p-4 pb-28">
        <div className="rounded-3xl bg-gradient-to-br from-amzn-purple to-indigo-700 text-white p-5">
          <Users size={26} className="text-white/90" />
          <h1 className="text-[20px] font-bold mt-2 leading-tight">One cart, the whole family</h1>
          <p className="text-[13px] text-white/80 mt-1">
            Everyone adds what they need from their own phone. It all combines into a single delivery.
          </p>
        </div>

        {/* active membership banner */}
        {active && (
          <div className="bg-amzn-greenlite border border-amzn-green/40 rounded-2xl p-2 mt-3 flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-amzn-green grid place-items-center shrink-0">
              <Users size={18} className="text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-bold text-amzn-green">
                You're in cart {active.gid}
              </p>
              <p className="text-[12px] text-ink2">
                {active.host ? "You're the host" : `Joined as ${active.name}`}
              </p>
            </div>
            <button
              onClick={() => router.push(`/group/${active.gid}${active.host ? "?host=1" : `?me=${encodeURIComponent(active.name)}`}`)}
              className="h-9 px-4 rounded-xl bg-amzn-green text-white text-[12px] font-bold flex items-center gap-1"
            >
              Open
            </button>
            <button onClick={leave} className="h-9 px-4 rounded-xl bg-amzn-red text-white text-[12px] font-bold flex items-center gap-1" aria-label="Leave cart">
              Leave
            </button>
          </div>
        )}

        {/* create */}
        <div className="bg-white rounded-2xl border border-line shadow-card p-4 mt-3">
          <p className="font-bold text-[15px]">Start a group cart</p>
          <p className="text-[12px] text-ink2 mt-0.5">
            {items.length > 0
              ? `Starts with your ${items.length} item${items.length > 1 ? "s" : ""} (${rupee(subtotal)}) — then invite family.`
              : "Create a shared cart, then invite your family to add items."}
          </p>
          <button
            onClick={create}
            disabled={busy}
            className="mt-3 w-full rounded-xl bg-amzn-yellow2 text-amzn-dark font-bold py-3 disabled:opacity-50"
          >
            Create &amp; invite
          </button>
        </div>

        {/* join */}
        <div className="bg-white rounded-2xl border border-line shadow-card p-4 mt-3">
          <p className="font-bold text-[15px] flex items-center gap-1.5">
            <LogIn size={16} /> Join a cart
          </p>
          <p className="text-[12px] text-ink2 mt-0.5">Got a code from family? Hop into their cart.</p>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            className="mt-3 w-full h-11 rounded-xl bg-paper px-3 text-[13px] outline-none"
          />
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="Cart code (e.g. FAM1001)"
            className="mt-2 w-full h-11 rounded-xl bg-paper px-3 text-[13px] outline-none tracking-widest font-semibold"
          />
          {err && <p className="text-[12px] text-amzn-red mt-1.5">{err}</p>}
          <button
            onClick={join}
            disabled={busy || !code.trim() || !name.trim()}
            className="mt-3 w-full rounded-xl bg-amzn-dark text-white font-bold py-2 disabled:opacity-40"
          >
            Join cart
          </button>
        </div>
      </main>
    </div>
  );
}

export default function GroupPage() {
  return (
    <Suspense fallback={<div className="flex-1 grid place-items-center text-ink2">Loading…</div>}>
      <GroupEntry />
    </Suspense>
  );
}
