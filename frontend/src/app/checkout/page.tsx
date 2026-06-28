"use client";
import { AnimatePresence, motion } from "framer-motion";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Clock,
  Lock,
  MapPin,
  ScanFace,
  ShoppingBag,
  TicketPercent,
  Users,
  Wallet,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useBoot } from "@/lib/boot";
import { useCart } from "@/lib/cart";
import { rupee } from "@/lib/format";
import type { CouponEval } from "@/lib/types";

export default function CheckoutPage() {
  const { items, subtotal, setQty, clear } = useCart();
  const boot = useBoot();
  const router = useRouter();
  const [paying, setPaying] = useState(false);
  const [evalc, setEvalc] = useState<CouponEval | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [sheet, setSheet] = useState(false);

  const fee = subtotal >= (boot?.settings.free_delivery_above ?? 199) ? 0 : boot?.settings.delivery_fee ?? 25;
  const eta = boot?.settings.eta_default_min ?? 14;

  // re-evaluate coupons whenever the cart changes; always auto-select the best
  useEffect(() => {
    if (items.length === 0) return;
    api.coupons(items.map((i) => ({ product_id: i.product.id, qty: i.qty })))
      .then((ev) => {
        setEvalc(ev);
        setSelected(ev.best_code);
      })
      .catch(() => {});
  }, [items]);

  const selectedCoupon = evalc?.coupons.find((c) => c.code === selected && c.eligible) || null;
  const discount = selectedCoupon?.discount ?? 0;
  const total = Math.max(0, subtotal + fee - discount);
  const eligibleCount = evalc?.coupons.filter((c) => c.eligible).length ?? 0;

  const params = useSearchParams();
  const gid = params.get("gid");

  const placeOrder = async () => {
    setPaying(true);
    const order = await api.order(
      items.map((i) => ({ product_id: i.product.id, qty: i.qty })),
      undefined,
      selected ?? undefined,
    );
    // delete the group cart after checkout if the user came from a shared cart
    if (gid) {
      api.groupCheckout(gid).catch(() => {});
      try { localStorage.removeItem("amzn-now-active-group"); } catch {}
    }
    setTimeout(() => {
      clear();
      router.push(`/order/${order.order_id}`);
    }, 1700);
  };

  if (items.length === 0) {
    return (
      <div className="flex flex-col h-full">
        <Header onBack={() => router.push("/")} />
        <div className="flex-1 grid place-items-center px-6 text-center">
          <div>
            <ShoppingBag size={48} className="mx-auto text-line" />
            <p className="font-bold mt-3">Your cart is empty</p>
            <p className="text-[13px] text-ink2 mt-1">Let NowCast build it for you.</p>
            <button onClick={() => router.push("/")} className="mt-4 bg-amzn-yellow2 text-amzn-dark font-bold px-5 py-2.5 rounded-xl">
              Go to NowCast
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <Header onBack={() => router.push("/")} />
      <div className="flex-1 overflow-y-auto no-scrollbar pb-40">
        {/* ETA banner */}
        <div className="bg-amzn-greenlite mx-3 mt-3 rounded-2xl px-4 py-3 flex items-center gap-2">
          <Clock size={18} className="text-amzn-green" />
          <span className="text-[13px] font-semibold text-amzn-green">Arriving in {eta} minutes</span>
        </div>

        {/* auto-applied coupon */}
        <button
          onClick={() => setSheet(true)}
          className={`mx-3 mt-3 w-[calc(100%-1.5rem)] rounded-2xl border px-4 py-3 flex items-center gap-2.5 text-left ${
            discount > 0 ? "border-amzn-green/40 bg-amzn-greenlite" : "border-line bg-white"
          }`}
        >
          <span className={`h-9 w-9 rounded-xl grid place-items-center shrink-0 ${discount > 0 ? "bg-amzn-green text-white" : "bg-paper text-ink2"}`}>
            <TicketPercent size={18} />
          </span>
          <div className="flex-1 min-w-0">
            {discount > 0 ? (
              <>
                <p className="text-[13px] font-bold text-amzn-green">
                  ‘{selected}’ applied — you save {rupee(discount)}
                </p>
                <p className="text-[11px] text-ink2">Best offer auto-selected · tap to see all {eligibleCount}</p>
              </>
            ) : (
              <>
                <p className="text-[13px] font-semibold">Apply a coupon</p>
                <p className="text-[11px] text-ink2">{eligibleCount} offers available</p>
              </>
            )}
          </div>
          <ChevronRight size={18} className="text-ink2 shrink-0" />
        </button>

        {/* group cart entry */}
        <button
          onClick={() => router.push("/group")}
          className="mx-3 mt-3 w-[calc(100%-1.5rem)] rounded-2xl border border-amzn-purple/30 bg-amzn-purple/5 px-4 py-3 flex items-center gap-2.5 text-left"
        >
          <Users size={18} className="text-amzn-purple" />
          <div className="flex-1">
            <p className="text-[13px] font-semibold text-amzn-purple">Shopping for the family?</p>
            <p className="text-[11px] text-ink2">Turn this into a group cart — everyone adds, one delivery</p>
          </div>
          <span className="text-amzn-purple">→</span>
        </button>

        {/* items */}
        <div className="bg-white mx-3 mt-3 rounded-2xl border border-line px-3 divide-y divide-line/70">
          {items.map((i) => (
            <div key={i.product.id} className="flex items-center gap-3 py-2.5">
              <div className="h-12 w-12 rounded-lg bg-paper grid place-items-center overflow-hidden shrink-0">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={i.product.image} alt="" className="h-[85%] w-[85%] object-contain" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-semibold leading-tight truncate">{i.product.name}</p>
                <p className="text-[11px] text-ink2">{i.product.size}</p>
              </div>
              <div className="flex items-center gap-1 bg-paper rounded-lg h-8 px-1">
                <button onClick={() => setQty(i.product.id, i.qty - 1)} className="w-7 text-amzn-green font-bold">
                  −
                </button>
                <span className="w-5 text-center text-[13px] font-bold">{i.qty}</span>
                <button onClick={() => setQty(i.product.id, i.qty + 1)} className="w-7 text-amzn-green font-bold">
                  +
                </button>
              </div>
              <span className="text-[13px] font-bold w-14 text-right shrink-0">{rupee(i.product.price * i.qty)}</span>
            </div>
          ))}
        </div>

        {/* bill */}
        <div className="bg-white mx-3 mt-3 rounded-2xl border border-line p-4 text-[13px] space-y-2">
          <Row label="Item total" value={rupee(subtotal)} />
          <Row label="Delivery fee" value={fee === 0 ? "FREE" : rupee(fee)} green={fee === 0} />
          {discount > 0 && <Row label={`Coupon (${selected})`} value={`− ${rupee(discount)}`} green />}
          <div className="border-t border-line pt-2 flex justify-between font-bold text-[15px]">
            <span>To pay</span>
            <span>{rupee(total)}</span>
          </div>
          {discount > 0 && (
            <p className="text-[11px] text-amzn-green font-semibold text-right">You saved {rupee(discount)} 🎉</p>
          )}
        </div>

        {/* address + payment */}
        <div className="bg-white mx-3 mt-3 rounded-2xl border border-line divide-y divide-line">
          <div className="flex items-start gap-3 p-3.5">
            <MapPin size={18} className="text-amzn-orange mt-0.5" />
            <div className="text-[12.5px]">
              <p className="font-semibold">Deliver to {boot?.user.address.label ?? "Home"}</p>
              <p className="text-ink2">
                {boot?.user.address.line1}, {boot?.user.address.line2}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 p-3.5">
            <Wallet size={18} className="text-amzn-orange" />
            <p className="text-[12.5px] font-semibold flex-1">{boot?.user.payment.label}</p>
            <span className="text-[12px] text-ink2">{boot?.user.payment.masked}</span>
          </div>
        </div>
      </div>

      {/* pay button */}
      <div className="absolute bottom-16 inset-x-0 z-20 bg-white border-t border-line p-3">
        <button
          onClick={placeOrder}
          className="w-full rounded-2xl bg-amzn-yellow2 text-amzn-dark font-bold py-3.5 flex items-center justify-center gap-2"
        >
          <ScanFace size={20} /> Pay {rupee(total)} · Face ID
        </button>
      </div>

      {/* coupon sheet */}
      <AnimatePresence>
        {sheet && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setSheet(false)} className="absolute inset-0 z-30 bg-black/50" />
            <motion.div
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className="absolute bottom-0 inset-x-0 z-40 bg-white rounded-t-3xl p-4 pb-6 max-h-[80%] flex flex-col"
            >
              <div className="h-1 w-10 bg-line rounded-full mx-auto mb-3" />
              <p className="font-bold text-[16px]">Coupons &amp; offers</p>
              <p className="text-[12px] text-ink2 mt-0.5">We auto-apply the biggest saving. Tap to switch.</p>
              <div className="mt-3 overflow-y-auto no-scrollbar space-y-2">
                {evalc?.coupons.map((c) => {
                  const isSel = c.code === selected && c.eligible;
                  const isBest = c.code === evalc.best_code;
                  return (
                    <button
                      key={c.code}
                      disabled={!c.eligible}
                      onClick={() => {
                        setSelected(c.code);
                        setSheet(false);
                      }}
                      className={`w-full text-left rounded-2xl border p-3 flex items-center gap-3 ${
                        isSel ? "border-amzn-green bg-amzn-greenlite" : c.eligible ? "border-line" : "border-line opacity-60"
                      }`}
                    >
                      <span className={`h-9 w-9 rounded-xl grid place-items-center shrink-0 ${c.eligible ? "bg-amzn-green/10 text-amzn-green" : "bg-paper text-ink2"}`}>
                        {c.eligible ? <TicketPercent size={17} /> : <Lock size={15} />}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-[13px] font-bold flex items-center gap-1.5">
                          {c.code}
                          {isBest && c.eligible && <span className="text-[9px] bg-amzn-green text-white px-1.5 py-0.5 rounded-full">BEST</span>}
                        </p>
                        <p className="text-[11px] text-ink2 leading-tight">{c.desc}</p>
                        {!c.eligible && <p className="text-[11px] text-amzn-red mt-0.5">{c.reason}</p>}
                      </div>
                      {c.eligible ? (
                        <span className="text-right shrink-0">
                          <span className="text-[13px] font-bold text-amzn-green">− {rupee(c.discount)}</span>
                          {isSel && <Check size={15} className="text-amzn-green ml-auto" />}
                        </span>
                      ) : (
                        <Lock size={14} className="text-ink2 shrink-0" />
                      )}
                    </button>
                  );
                })}
                {selected && (
                  <button onClick={() => { setSelected(null); setSheet(false); }} className="w-full text-center text-[12px] text-ink2 py-2">
                    Remove coupon
                  </button>
                )}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* face id overlay */}
      <AnimatePresence>
        {paying && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 z-50 bg-amzn-dark/95 grid place-items-center">
            <div className="text-center text-white">
              <motion.div
                initial={{ scale: 0.8 }}
                animate={{ scale: [0.8, 1, 0.95] }}
                transition={{ duration: 1.2 }}
                className="mx-auto h-24 w-24 rounded-3xl border-2 border-amzn-yellow grid place-items-center"
              >
                <ScanFace size={56} className="text-amzn-yellow" />
              </motion.div>
              <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.9 }} className="mt-4 font-semibold">
                Payment confirmed
              </motion.p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Header({ onBack }: { onBack: () => void }) {
  return (
    <header className="bg-amzn-dark text-white px-3 pt-2 pb-3 shrink-0 flex items-center gap-2">
      <button onClick={onBack} className="p-1">
        <ChevronLeft size={22} />
      </button>
      <span className="font-bold">Checkout</span>
    </header>
  );
}

function Row({ label, value, green }: { label: string; value: string; green?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-ink2">{label}</span>
      <span className={green ? "text-amzn-green font-semibold" : ""}>{value}</span>
    </div>
  );
}
