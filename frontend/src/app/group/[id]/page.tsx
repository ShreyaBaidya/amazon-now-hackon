"use client";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronLeft, Copy, Plus, Search, Share2, Users, X } from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useBoot } from "@/lib/boot";
import { useCart } from "@/lib/cart";
import { rupee } from "@/lib/format";
import type { GroupCart, Product } from "@/lib/types";

type ActivityToast = {
  name: string;
  color: string;
  text: string;
  pending?: boolean;
};

export default function GroupCartPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const params = useSearchParams();
  const boot = useBoot();
  const { addMany } = useCart();
  const me = params.get("me") || boot?.user.first_name || "You";
  const host = params.get("host") === "1";

  const [cart, setCart] = useState<GroupCart | null>(null);
  const [shareOpen, setShareOpen] = useState(host);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [toast, setToast] = useState<ActivityToast | null>(null);
  const [copied, setCopied] = useState(false);
  const startedRef = useRef(false);
  const esRef = useRef<EventSource | null>(null);
  const playEsRef = useRef<EventSource | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [updatingLine, setUpdatingLine] = useState<string | null>(null);

  // connect to SSE for real-time group updates
  useEffect(() => {
    api.groupGet(id).then(setCart).catch(() => {});

    const es = new EventSource(api.groupStreamUrl(id));
    esRef.current = es;

    es.addEventListener("state", (e: MessageEvent) => {
      setCart(JSON.parse(e.data));
    });

    es.addEventListener("update", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      if (data.state) {
        setCart(data.state);
      }
    });

    es.onerror = () => {};

    return () => {
      es.close();
      playEsRef.current?.close();
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, [id]);

  const showToast = (next: ActivityToast, ms = 2600) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast(next);
    toastTimerRef.current = setTimeout(() => setToast(null), ms);
  };

  const startFamily = () => {
    if (startedRef.current) return;
    startedRef.current = true;
    setShareOpen(false);
    const es = new EventSource(api.groupStreamUrl(id, true));
    playEsRef.current = es;
    es.addEventListener("state", (e: MessageEvent) => setCart(JSON.parse(e.data)));
    es.addEventListener("update", (e: MessageEvent) => {
      const { state, joined } = JSON.parse(e.data);
      setCart(state);
      if (joined) {
        const added = state.items.filter((it: GroupCart["items"][number]) => it.added_by === joined.name);
        const first = added[0]?.product.name;
        const text = first
          ? added.length > 1
            ? `added ${first} + ${added.length - 1} more`
            : `added ${first}`
          : `joined the cart`;
        showToast({ name: joined.name, color: joined.color, text });
      }
    });
    es.addEventListener("done", () => es.close());
    es.onerror = () => es.close();
  };

  const addToGroup = async (p: Product) => {
    const color = cart?.members.find((m) => m.name === me)?.color || boot?.user.avatar_color || "#FF9900";
    showToast({ name: me, color, text: `is adding ${p.name}`, pending: true }, 1800);
    const updated = await api.groupAdd(id, p.id, 1, me);
    setCart(updated);
    showToast({ name: me, color, text: `added ${p.name}` });
  };

  const changeGroupQty = async (it: GroupCart["items"][number], delta: number) => {
    if (delta < 0 && it.qty <= 0) return;
    const lineKey = `${it.product.id}-${it.added_by}`;
    if (updatingLine === lineKey) return;
    setUpdatingLine(lineKey);
    try {
      const updated = await api.groupAdd(id, it.product.id, delta, it.added_by);
      setCart(updated);
    } finally {
      setUpdatingLine(null);
    }
  };

  const checkout = () => {
    if (!cart) return;
    addMany(cart.items.map((i) => ({ product: i.product, qty: i.qty })), true);
    router.push("/checkout?src=group");
  };

  const copyCode = () => {
    navigator.clipboard?.writeText(`${location.origin}/group?code=${id}`).catch(() => {});
    setCopied(true);
    setWaiting(true);
    setTimeout(() => startFamily(), 2000); // give time to share before family streams in
  };

  if (!cart) return <div className="flex-1 grid place-items-center text-ink2">Opening cart…</div>;

  return (
    <div className="flex flex-col h-full">
      <header className="bg-amzn-dark text-white px-3 pt-2 pb-3 shrink-0">
        <div className="flex items-center gap-2">
          <button onClick={() => router.push("/")} className="p-1">
            <ChevronLeft size={22} />
          </button>
          <div className="flex-1">
            <p className="font-bold flex items-center gap-1.5">
              <Users size={16} className="text-amzn-yellow" /> Family cart
            </p>
            <p className="text-[11px] text-white/60">Code {cart.code} · everyone adds, one delivery</p>
          </div>
          <button onClick={() => setShareOpen(true)} className="h-9 px-3 rounded-xl bg-white/10 flex items-center gap-1.5 text-[12px] font-semibold">
            <Share2 size={15} /> Share
          </button>
        </div>

        {/* members */}
        <div className="flex items-center gap-2 mt-3">
          <div className="flex -space-x-2">
            <AnimatePresence>
              {cart.members.map((m) => (
                <motion.span
                  key={m.name}
                  initial={{ scale: 0, x: -6 }}
                  animate={{ scale: 1, x: 0 }}
                  className="h-8 w-8 rounded-full grid place-items-center text-[12px] font-bold text-white ring-2 ring-amzn-dark"
                  style={{ background: m.color }}
                  title={m.name}
                >
                  {m.name[0]}
                </motion.span>
              ))}
            </AnimatePresence>
          </div>
          <span className="text-[12px] text-white/70">
            {cart.members.length} {cart.members.length === 1 ? "person" : "people"} shopping
          </span>
        </div>
      </header>

      {/* items */}
      <div className="flex-1 overflow-y-auto no-scrollbar px-3 py-3 pb-40">
        <AnimatePresence initial={false}>
          {cart.items.map((it) => {
            const lineKey = `${it.product.id}-${it.added_by}`;
            const busy = updatingLine === lineKey;
            const off = it.qty <= 0;
            return (
              <motion.div
                key={lineKey}
                layout
                initial={{ opacity: 0, y: 12, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                className="flex items-center gap-3 bg-white rounded-2xl border border-line p-2.5 mb-2 shadow-card"
              >
                <div className={`h-12 w-12 rounded-lg bg-paper grid place-items-center overflow-hidden shrink-0 ${off ? "opacity-40" : ""}`}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={it.product.image} alt="" className="h-[85%] w-[85%] object-contain" />
                </div>
                <div className={`flex-1 min-w-0 ${off ? "opacity-40" : ""}`}>
                  <p className="text-[13px] font-semibold leading-tight truncate">
                    {it.product.name}
                  </p>
                  <span className="inline-flex items-center gap-1 text-[11px] mt-0.5" style={{ color: it.added_by_color }}>
                    <span className="h-3.5 w-3.5 rounded-full grid place-items-center text-[8px] font-bold text-white" style={{ background: it.added_by_color }}>
                      {it.added_by[0]}
                    </span>
                    {it.added_by}
                  </span>
                </div>
                <div className={`shrink-0 flex flex-col items-end gap-1 ${off ? "opacity-50" : ""}`}>
                  <span className={`text-[13px] font-bold ${off ? "line-through" : ""}`}>{rupee(it.line_total)}</span>
                  <div className="h-7 w-[78px] rounded-lg bg-amzn-green text-white text-[12px] font-bold flex items-center justify-between px-1">
                    <button
                      onClick={() => changeGroupQty(it, -1)}
                      disabled={busy || it.qty <= 0}
                      className="grid place-items-center h-full w-6 disabled:opacity-45"
                      aria-label={`decrease ${it.product.name}`}
                    >
                      -
                    </button>
                    <motion.span key={it.qty} initial={{ scale: 0.75 }} animate={{ scale: 1 }}>
                      {it.qty}
                    </motion.span>
                    <button
                      onClick={() => changeGroupQty(it, 1)}
                      disabled={busy}
                      className="grid place-items-center h-full w-6 disabled:opacity-45"
                      aria-label={`increase ${it.product.name}`}
                    >
                      +
                    </button>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>

        <button
          onClick={() => setPickerOpen(true)}
          className="w-full mt-1 border-2 border-dashed border-line rounded-2xl py-3 text-[13px] font-semibold text-ink2 flex items-center justify-center gap-1.5"
        >
          <Plus size={16} /> Add your items
        </button>
      </div>

      {/* checkout bar */}
      <div className="absolute bottom-16 inset-x-0 z-20 bg-white border-t border-line p-3">
        <button
          onClick={checkout}
          disabled={cart.item_count === 0}
          className="w-full rounded-2xl bg-amzn-green text-white font-bold py-3.5 flex items-center justify-between px-4 disabled:opacity-50"
        >
          <span className="flex items-center gap-2">
            <span className="grid place-items-center h-7 min-w-7 px-1.5 rounded-lg bg-white/20 text-sm">{cart.item_count}</span>
            Checkout together
          </span>
          <span>{rupee(cart.total)}</span>
        </button>
      </div>

      {/* activity toast */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ y: -40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -40, opacity: 0 }}
            className="absolute top-3 inset-x-4 z-40 bg-white rounded-2xl shadow-pop p-3 flex items-center gap-2.5"
          >
            <span className="h-9 w-9 rounded-full grid place-items-center text-white font-bold" style={{ background: toast.color }}>
              {toast.name[0]}
            </span>
            <p className="min-w-0 text-[13px] font-semibold">
              {toast.name}{" "}
              <span className="font-normal text-ink2">
                {toast.text}
                {toast.pending ? "..." : ""}
              </span>
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* share sheet */}
      <Sheet open={shareOpen} onClose={() => setShareOpen(false)}>
        <p className="font-bold text-[16px]">Invite your family</p>
        <p className="text-[12px] text-ink2 mt-0.5">Share this cart — everything they add lands here.</p>
        <div className="mt-4 bg-paper rounded-2xl p-4 text-center">
          <p className="text-[11px] text-ink2">Cart code</p>
          <p className="text-[26px] font-extrabold tracking-widest">{cart.code}</p>
        </div>
        <button
          onClick={copyCode}
          disabled={waiting}
          className="mt-3 w-full rounded-xl bg-amzn-dark text-white font-bold py-3 flex items-center justify-center gap-2 disabled:opacity-80"
        >
          {copied ? <Check size={18} /> : <Copy size={18} />}
          {waiting ? "Shared! Family is joining…" : copied ? "Link copied!" : "Copy invite link"}
        </button>
        <div className="grid grid-cols-3 gap-2 mt-2">
          {["WhatsApp", "Messages", "More"].map((s) => (
            <div key={s} className="bg-paper rounded-xl py-2.5 text-center text-[11px] font-semibold text-ink2">
              {s}
            </div>
          ))}
        </div>
      </Sheet>

      {/* add-items picker */}
      <PickerSheet open={pickerOpen} onClose={() => setPickerOpen(false)} onPick={addToGroup} />
    </div>
  );
}

function Sheet({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} className="absolute inset-0 z-30 bg-black/50" />
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            className="absolute bottom-0 inset-x-0 z-40 bg-white rounded-t-3xl p-4 pb-6"
          >
            <div className="h-1 w-10 bg-line rounded-full mx-auto mb-3" />
            {children}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function PickerSheet({ open, onClose, onPick }: { open: boolean; onClose: () => void; onPick: (p: Product) => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Product[]>([]);
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => api.catalog(q, "", 12).then((d) => setResults(d.products)).catch(() => {}), 180);
    return () => clearTimeout(t);
  }, [q, open]);

  return (
    <Sheet open={open} onClose={onClose}>
      <div className="flex items-center justify-between">
        <p className="font-bold text-[16px]">Add your items</p>
        <button onClick={onClose}>
          <X size={20} className="text-ink2" />
        </button>
      </div>
      <div className="mt-3 flex items-center bg-paper rounded-xl px-3 h-10">
        <Search size={16} className="text-ink2" />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search to add…" className="flex-1 bg-transparent outline-none text-[13px] ml-2" />
      </div>
      <div className="mt-3 max-h-72 overflow-y-auto no-scrollbar divide-y divide-line/70">
        {results.map((p) => (
          <button key={p.id} onClick={() => onPick(p)} className="w-full flex items-center gap-3 py-2 text-left">
            <div className="h-10 w-10 rounded-lg bg-paper grid place-items-center overflow-hidden shrink-0">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.image} alt="" className="h-[85%] w-[85%] object-contain" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[12.5px] font-semibold truncate">{p.name}</p>
              <p className="text-[11px] text-ink2">{rupee(p.price)} · {p.size}</p>
            </div>
            <Plus size={18} className="text-amzn-green" />
          </button>
        ))}
      </div>
    </Sheet>
  );
}
