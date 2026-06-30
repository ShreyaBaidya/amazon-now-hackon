"use client";
import { AnimatePresence, motion } from "framer-motion";
import {
  Calendar,
  Check,
  ChevronRight,
  Clock,
  Loader2,
  MapPin,
  Refrigerator,
  RefreshCw,
  Sparkles,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useCart } from "@/lib/cart";
import { rupee } from "@/lib/format";
import { useGoogleCalendar } from "@/lib/useGoogleCalendar";
import { useTimeRemaining } from "@/lib/useTimeRemaining";
import type { NowCast as NowCastT, NowCastGroup } from "@/lib/types";
import CalendarConnect from "./CalendarConnect";
import VegMark, { AllergenBadge, DietaryTags } from "./VegMark";

const SIGNAL_ICON = { calendar: Calendar, fridge: Refrigerator, history: RefreshCw } as const;
const SIGNAL_COLOR = {
  calendar: "text-amzn-purple bg-amzn-purple/10",
  fridge: "text-sky-600 bg-sky-100",
  history: "text-amber-600 bg-amber-100",
} as const;
const CTA = { calendar: "Prepare cart", fridge: "Add what's low", history: "Top up supplies" } as const;

export default function NowCast() {
  const [data, setData] = useState<NowCastT | null>(null);
  const [loadError, setLoadError] = useState(false);
  const gcal = useGoogleCalendar();

  const fetchNowcast = useCallback(() => {
    setLoadError(false);
    api.nowcast()
      .then(setData)
      .catch(() => setLoadError(true));
  }, []);

  useEffect(() => {
    fetchNowcast();
  }, [fetchNowcast]);

  // Re-fetch NowCast after a calendar refresh so new products appear immediately
  const handleCalendarRefresh = useCallback(() => {
    // Small delay so backend finishes the new fetch before we request NowCast
    setTimeout(fetchNowcast, 600);
  }, [fetchNowcast]);

  if (!data && !loadError) return <NowCastSkeleton />;

  if (loadError) {
    return (
      <section className="px-3">
        <div className="rounded-3xl border border-red-200 bg-red-50 p-4 flex flex-col items-center gap-3 text-center">
          <p className="text-[13px] font-semibold text-red-700">
            Couldn't load your NowCast. Check your connection.
          </p>
          <button
            onClick={fetchNowcast}
            className="flex items-center gap-1.5 text-[12px] font-bold text-red-600 bg-red-100 px-3 py-1.5 rounded-xl"
          >
            <RefreshCw size={13} /> Retry
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="px-3">
      {/* hero banner */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-3xl bg-gradient-to-br from-amzn-dark to-amzn-blue2 text-white p-4"
      >
        <div className="flex items-center gap-1.5 text-amzn-yellow text-[11px] font-bold tracking-wide uppercase">
          <Sparkles size={13} /> NowCast
        </div>
        <h1 className="text-[21px] font-bold leading-tight mt-1">3 things we lined up for you</h1>
        <p className="text-[13px] text-white/70 mt-1">
          From your calendar, fridge and habits. Tap any one to build your cart.
        </p>
      </motion.div>

      {/* Google Calendar connect / status banner */}
      <div className="mt-2.5">
        <CalendarConnect gcal={gcal} onRefresh={handleCalendarRefresh} />
      </div>

      {/* signal cards */}
      <div className="mt-1 space-y-2.5">
        {/* If calendar is connected but there's no calendar group, show empty state */}
        {gcal.state === "connected" && !data!.groups.find(g => g.signal === "calendar") && (
          <NoEventsToday />
        )}
        {data!.groups.map((g, i) => (
          <SignalCard
            key={g.signal}
            group={g}
            event={g.signal === "calendar" ? data!.event : null}
            index={i}
          />
        ))}
      </div>
    </section>
  );
}

function SignalCard({
  group,
  event,
  index,
}: {
  group: NowCastGroup;
  event: NowCastT["event"];
  index: number;
}) {
  const { addMany } = useCart();
  const [open, setOpen] = useState(false);
  const [added, setAdded] = useState(false);
  const [qtyById, setQtyById] = useState<Record<string, number>>({});
  const timeRemaining = useTimeRemaining(
    group.signal === "calendar" ? event?.dt_utc : null
  );

  const Icon = SIGNAL_ICON[group.signal];
  const qtyOf = (id: string, fallback: number) => qtyById[id] ?? fallback;
  const included = group.items
    .map((l) => ({ ...l, selected_qty: qtyOf(l.product.id, l.qty) }))
    .filter((l) => l.selected_qty > 0);
  const count = included.reduce((s, l) => s + l.selected_qty, 0);
  const total = included.reduce((s, l) => s + l.product.price * l.selected_qty, 0);

  // Build a rich subtitle line for the calendar card
  const calendarSubtitle = event
    ? [
        event.when_label,
        event.guests ? `${event.guests} guests` : null,
        `${group.items.length} items`,
      ]
        .filter(Boolean)
        .join(" · ")
    : `${group.items.length} items · ${group.blurb}`;

  const subtitle = added
    ? `Added ${count} item${count > 1 ? "s" : ""} to cart`
    : group.signal === "calendar"
      ? calendarSubtitle
      : `${group.items.length} items · ${group.blurb}`;

  const setLineQty = (id: string, qty: number) =>
    setQtyById((cur) => ({ ...cur, [id]: Math.max(0, Math.min(99, qty)) }));

  const toggle = (id: string, fallback: number) =>
    setLineQty(id, qtyOf(id, fallback) > 0 ? 0 : fallback);

  const addToCart = () => {
    addMany(included.map((l) => ({ product: l.product, qty: l.selected_qty })));
    setAdded(true);
    setOpen(false);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 + index * 0.08 }}
      className={`rounded-3xl border bg-white shadow-card overflow-hidden ${
        added ? "border-amzn-green/40" : "border-line"
      }`}
    >
      {/* header */}
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center gap-3 p-3.5 text-left">
        <span className={`h-11 w-11 rounded-2xl grid place-items-center shrink-0 ${SIGNAL_COLOR[group.signal]}`}>
          <Icon size={20} />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[14px] font-bold leading-tight">{group.title}</p>
          <p className={`text-[11.5px] mt-0.5 flex items-center gap-1 ${added ? "text-amzn-green font-semibold" : "text-ink2"}`}>
            {added && <Check size={12} />}
            {subtitle}
          </p>
        </div>
        {added ? (
          <span className="h-8 w-8 rounded-full bg-amzn-greenlite grid place-items-center shrink-0">
            <Check size={17} className="text-amzn-green" strokeWidth={3} />
          </span>
        ) : (
          <span className="flex items-center gap-1 bg-amzn-yellow2 text-amzn-dark text-[12px] font-bold px-3 py-2 rounded-xl shrink-0">
            {CTA[group.signal]}
            <ChevronRight size={14} className={`transition ${open ? "rotate-90" : ""}`} />
          </span>
        )}
      </button>

      {/* Calendar event metadata strip — shown only for calendar cards */}
      {group.signal === "calendar" && event && !added && (
        <CalendarEventMeta event={event} timeRemaining={timeRemaining} />
      )}

      {/* expandable body */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="px-3.5 pb-3.5">
              <div className="border-t border-line divide-y divide-line/70">
                {group.items.map((l) => {
                  const qty = qtyOf(l.product.id, l.qty);
                  const off = qty <= 0;
                  return (
                    <div key={l.product.id} className="flex items-center gap-2.5 py-2">
                      <button
                        onClick={() => toggle(l.product.id, l.qty)}
                        disabled={added}
                        className={`h-5 w-5 rounded-md border-2 grid place-items-center shrink-0 ${
                          off ? "border-line bg-white" : "border-amzn-green bg-amzn-green"
                        }`}
                        aria-label={`${off ? "include" : "exclude"} ${l.product.name}`}
                      >
                        {!off && <Check size={13} className="text-white" strokeWidth={3} />}
                      </button>
                      <div className={`h-10 w-10 rounded-lg bg-paper grid place-items-center shrink-0 overflow-hidden ${off ? "opacity-40" : ""}`}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={l.product.image} alt="" className="h-[85%] w-[85%] object-contain" />
                      </div>
                      <div className={`flex-1 min-w-0 ${off ? "opacity-40" : ""}`}>
                        <div className="flex items-center gap-1">
                          <VegMark product={l.product} size={11} />
                          <p className="text-[12.5px] font-semibold leading-tight truncate">
                            {l.product.name}
                          </p>
                        </div>
                        <p className="text-[11px] text-ink2 truncate">{l.reason}</p>
                        <DietaryTags product={l.product} max={1} />
                        <AllergenBadge product={l.product} />
                      </div>
                      <div className={`shrink-0 flex flex-col items-end gap-1 ${off ? "opacity-50" : ""}`}>
                        <span className={`text-[12.5px] font-bold ${off ? "line-through" : ""}`}>
                          {rupee(l.product.price * qty)}
                        </span>
                        {!added && (
                          <div className="h-7 w-[78px] rounded-lg bg-amzn-green text-white text-[12px] font-bold flex items-center justify-between px-1">
                            <button
                              onClick={() => setLineQty(l.product.id, qty - 1)}
                              className="grid place-items-center h-full w-6"
                              aria-label={`decrease ${l.product.name}`}
                            >
                              -
                            </button>
                            <motion.span key={qty} initial={{ scale: 0.75 }} animate={{ scale: 1 }}>
                              {qty}
                            </motion.span>
                            <button
                              onClick={() => setLineQty(l.product.id, qty + 1)}
                              className="grid place-items-center h-full w-6"
                              aria-label={`increase ${l.product.name}`}
                            >
                              +
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {!added && (
                <motion.button
                  whileTap={{ scale: 0.98 }}
                  onClick={addToCart}
                  disabled={count === 0}
                  className="mt-3 w-full rounded-xl bg-amzn-green text-white font-bold py-3 flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  Add {count} item{count > 1 ? "s" : ""} to cart · {rupee(total)}
                </motion.button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/**
 * CalendarEventMeta
 * A compact strip showing event details: guests, location, time remaining.
 * Rendered between the card header and the expandable body.
 */
function CalendarEventMeta({
  event,
  timeRemaining,
}: {
  event: NowCastT["event"];
  timeRemaining: string | null;
}) {
  if (!event) return null;

  const chips = [
    event.guests && event.guests > 0
      ? { icon: <Users size={11} />, label: `${event.guests} guests` }
      : null,
    event.location
      ? { icon: <MapPin size={11} />, label: event.location.split(",")[0] }
      : null,
    timeRemaining
      ? { icon: <Clock size={11} />, label: timeRemaining }
      : null,
  ].filter(Boolean) as { icon: React.ReactNode; label: string }[];

  if (chips.length === 0) return null;

  return (
    <div className="px-3.5 pb-2 flex flex-wrap gap-1.5">
      {chips.map((c) => (
        <span
          key={c.label}
          className="flex items-center gap-1 text-[10.5px] font-semibold text-amzn-purple/80 bg-amzn-purple/8 px-2 py-0.5 rounded-full"
        >
          {c.icon}
          {c.label}
        </span>
      ))}
    </div>
  );
}

/** Shown when Google Calendar is connected but there are no events today. */
function NoEventsToday() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-3xl border border-dashed border-amzn-purple/30 bg-amzn-purple/5 p-4 flex items-center gap-3"
    >
      <span className="h-11 w-11 rounded-2xl grid place-items-center shrink-0 text-amzn-purple bg-amzn-purple/10">
        <Calendar size={20} />
      </span>
      <div>
        <p className="text-[13px] font-bold text-amzn-purple">No events today</p>
        <p className="text-[11.5px] text-ink2 mt-0.5">
          Your Google Calendar is clear for today.
        </p>
      </div>
    </motion.div>
  );
}

function NowCastSkeleton() {
  return (
    <section className="px-3">
      <div className="rounded-3xl bg-gradient-to-br from-amzn-dark to-amzn-blue2 p-4 h-28 shimmer" />
      <div className="mt-3 space-y-2.5">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="rounded-3xl border border-line bg-white p-3.5 flex items-center gap-3">
            <div className="h-11 w-11 rounded-2xl bg-paper shimmer" />
            <div className="flex-1 space-y-1.5">
              <div className="h-3 w-2/3 bg-paper rounded shimmer" />
              <div className="h-2.5 w-1/2 bg-paper rounded shimmer" />
            </div>
            <div className="h-9 w-24 bg-paper rounded-xl shimmer" />
          </div>
        ))}
      </div>
      {/* Loading indicator */}
      <div className="flex items-center justify-center gap-2 mt-4 text-[11px] text-ink2">
        <Loader2 size={13} className="animate-spin" />
        Building your cart…
      </div>
    </section>
  );
}
