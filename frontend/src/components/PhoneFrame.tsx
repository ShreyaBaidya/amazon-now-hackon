"use client";
import { BatteryFull, Signal, Wifi } from "lucide-react";
import BottomNav from "./BottomNav";
import CartBar from "./CartBar";

export default function PhoneFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen w-full flex items-center justify-center p-0 ">
      <div
        className="relative w-full bg-white overflow-hidden flex flex-col
                   sm:rounded-[42px] sm:border-[10px] sm:border-black sm:shadow-pop"
        style={{ maxWidth: 412, height: "min(880px, 100svh)" }}
      >
        {/* status bar */}
        <div className="relative z-30 flex items-center justify-between px-6 pt-1 bg-amzn-dark text-white text-[12px] font-semibold shrink-0">
          <span>9:41</span>
          <div className="absolute left-1/2 -translate-x-1/2 top-0 h-5 w-28 bg-black rounded-b-2xl hidden sm:block" />
          <div className="flex items-center gap-1.5">
            <Signal size={13} />
            <Wifi size={13} />
            <BatteryFull size={15} />
          </div>
        </div>

        {/* screen */}
        <div className="relative flex-1 min-h-0 flex flex-col bg-paper">
          {children}
          <CartBar />
          <BottomNav />
        </div>
      </div>
    </div>
  );
}
