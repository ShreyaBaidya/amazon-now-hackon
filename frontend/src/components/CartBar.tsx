"use client";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Leaf } from "lucide-react";
import { useRouter, usePathname } from "next/navigation";
import { useCart, ECONOMY_BUDGETS } from "@/lib/cart";
import { rupee } from "@/lib/format";

const HIDE_ON = ["/checkout", "/order", "/profile", "/group", "/recipe", "/speaknow", "/dish-result"];

export default function CartBar() {
  const { count, subtotal, economyMode, setEconomyMode } = useCart();
  const router = useRouter();
  const path = usePathname();
  const hidden = count === 0 || HIDE_ON.some((p) => path.startsWith(p));

  return (
    <AnimatePresence>
      {!hidden && (
        <motion.div
          initial={{ y: 80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 80, opacity: 0 }}
          transition={{ type: "spring", stiffness: 380, damping: 30 }}
          className="absolute bottom-[72px] inset-x-3 z-20 flex flex-col gap-1.5"
        >
          {/* Economy toggle pill */}
          <div className="flex justify-end">
            <button
              onClick={() => setEconomyMode(!economyMode)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] font-bold shadow-pop transition-all ${
                economyMode
                  ? "bg-emerald-600 text-white"
                  : "bg-white text-emerald-700 border border-emerald-300"
              }`}
            >
              <Leaf size={13} />
              {economyMode ? "💚 Economy ON" : "Economy mode"}
            </button>
          </div>

          {/* Main cart bar */}
          <button
            onClick={() => router.push("/checkout")}
            className={`w-full h-13 rounded-2xl text-white shadow-pop flex items-center justify-between px-4 py-3 transition-colors ${
              economyMode ? "bg-emerald-600" : "bg-amzn-green"
            }`}
          >
            <div className="flex items-center gap-2 text-left">
              <span className="grid place-items-center h-7 min-w-7 px-1.5 rounded-lg bg-white/20 text-sm font-bold">
                {count}
              </span>
              <div className="flex flex-col leading-tight">
                <span className="text-sm font-semibold">{rupee(subtotal)}</span>
                {economyMode && (
                  <span className="text-[10px] text-white/80">💚 Economy cart</span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1.5 text-sm font-bold">
              View cart <ArrowRight size={17} />
            </div>
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
