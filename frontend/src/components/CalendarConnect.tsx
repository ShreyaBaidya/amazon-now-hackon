"use client";
/**
 * CalendarConnect
 *
 * A compact banner/button that surfaces Google Calendar connection state.
 * - Shows a "Connect Google Calendar" CTA when disconnected.
 * - Shows a green "Connected" pill + Refresh / Disconnect actions when live.
 * - Hidden when credentials are not configured on the server (no_credentials).
 * - Propagates isLoading and errorMsg to parent via callbacks.
 */
import { motion, AnimatePresence } from "framer-motion";
import { Calendar, CheckCircle2, RefreshCw, Unlink, Loader2, AlertCircle } from "lucide-react";
import type { UseGoogleCalendarReturn } from "@/lib/useGoogleCalendar";

interface Props {
  gcal: UseGoogleCalendarReturn;
  /** Optional: called after a successful refresh so parent can re-fetch NowCast */
  onRefresh?: () => void;
}

export default function CalendarConnect({ gcal, onRefresh }: Props) {
  const { state, errorMsg, connect, disconnect, refresh, isLoading } = gcal;

  // Don't render anything if the server has no credentials — no point showing a broken button
  if (state === "no_credentials" || state === "idle") return null;

  const handleRefresh = async () => {
    await refresh();
    onRefresh?.();
  };

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={state}
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.2 }}
        className="mx-3 mb-3"
      >
        {/* Error state */}
        {(state === "error" || errorMsg) && (
          <div className="flex items-center gap-2 rounded-2xl bg-red-50 border border-red-200 px-3.5 py-2.5 text-[12px]">
            <AlertCircle size={15} className="text-red-500 shrink-0" />
            <p className="flex-1 text-red-700 font-medium">
              {errorMsg ?? "Google Calendar error"}
            </p>
            <button
              onClick={connect}
              className="text-red-600 font-bold underline"
              aria-label="Retry Google Calendar connection"
            >
              Retry
            </button>
          </div>
        )}

        {/* Connected state */}
        {state === "connected" && !errorMsg && (
          <div className="flex items-center gap-2.5 rounded-2xl bg-emerald-50 border border-emerald-200 px-3.5 py-2.5">
            <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
            <p className="flex-1 text-[12px] font-semibold text-emerald-800">
              Google Calendar connected
            </p>
            {/* Refresh button */}
            <button
              onClick={handleRefresh}
              disabled={isLoading}
              aria-label="Refresh calendar data"
              className="h-7 w-7 rounded-xl bg-emerald-100 grid place-items-center text-emerald-700
                         hover:bg-emerald-200 disabled:opacity-50 transition"
            >
              {isLoading
                ? <Loader2 size={13} className="animate-spin" />
                : <RefreshCw size={13} />
              }
            </button>
            {/* Disconnect button */}
            <button
              onClick={disconnect}
              disabled={isLoading}
              aria-label="Disconnect Google Calendar"
              className="h-7 w-7 rounded-xl bg-emerald-100 grid place-items-center text-emerald-700
                         hover:bg-red-100 hover:text-red-600 disabled:opacity-50 transition"
            >
              <Unlink size={13} />
            </button>
          </div>
        )}

        {/* Disconnected / checking state */}
        {(state === "disconnected" || state === "checking") && !errorMsg && (
          <button
            onClick={connect}
            disabled={isLoading || state === "checking"}
            className="w-full flex items-center gap-2.5 rounded-2xl border border-dashed border-amzn-purple/40
                       bg-amzn-purple/5 px-3.5 py-2.5 text-left hover:bg-amzn-purple/10 transition
                       disabled:opacity-50"
            aria-label="Connect Google Calendar"
          >
            {isLoading || state === "checking"
              ? <Loader2 size={16} className="text-amzn-purple shrink-0 animate-spin" />
              : <Calendar size={16} className="text-amzn-purple shrink-0" />
            }
            <div className="flex-1 min-w-0">
              <p className="text-[12.5px] font-bold text-amzn-purple">
                Connect Google Calendar
              </p>
              <p className="text-[11px] text-amzn-purple/70">
                Auto-detect upcoming events &amp; prep your cart
              </p>
            </div>
            <span className="text-[11px] font-bold text-amzn-purple bg-amzn-purple/10 px-2.5 py-1 rounded-lg shrink-0">
              Connect
            </span>
          </button>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
