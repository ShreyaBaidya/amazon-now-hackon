"use client";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useRouter, usePathname } from "next/navigation";
import { useCart } from "@/lib/cart";
import { rupee } from "@/lib/format";

const HIDE_ON = ["/checkout", "/order", "/profile", "/group", "/recipe", "/nowspeak", "/dish-result"];

export default function CartBar() {
  const { count, subtotal } = useCart();
  const router = useRouter();
  const path = usePathname();
  const hidden = count === 0 || HIDE_ON.some((p) => path.startsWith(p));

  return (
    <AnimatePresence>
      {!hidden && (
        <motion.button
          initial={{ y: 80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 80, opacity: 0 }}
          transition={{ type: "spring", stiffness: 380, damping: 30 }}
          onClick={() => router.push("/checkout")}
          className="absolute bottom-[72px] inset-x-3 z-20 h-13 rounded-2xl bg-amzn-green text-white
                     shadow-pop flex items-center justify-between px-4 py-3"
        >
          <div className="flex items-center gap-2 text-left">
            <span className="grid place-items-center h-7 min-w-7 px-1.5 rounded-lg bg-white/20 text-sm font-bold">
              {count}
            </span>
            <span className="text-sm font-semibold">{rupee(subtotal)}</span>
          </div>
          <div className="flex items-center gap-1.5 text-sm font-bold">
            View cart <ArrowRight size={17} />
          </div>
        </motion.button>
      )}
    </AnimatePresence>
  );
}
