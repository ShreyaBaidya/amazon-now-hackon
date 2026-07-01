"use client";
import { ChefHat, Home, Mic, ShoppingCart } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCart } from "@/lib/cart";

const TABS = [
  { href: "/", label: "Home", icon: Home },
  { href: "/speaknow", label: "Speak", icon: Mic },
  { href: "/recipes", label: "Cook", icon: ChefHat },
  { href: "/checkout", label: "Cart", icon: ShoppingCart },
];

export default function BottomNav() {
  const path = usePathname();
  const { count } = useCart();
  return (
    <nav className="absolute bottom-0 inset-x-0 z-20 h-16 bg-white border-t border-line flex items-stretch">
      {TABS.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className="relative flex-1 flex flex-col items-center justify-center gap-0.5"
          >
            <span className="relative">
              <Icon
                size={22}
                className={active ? "text-amzn-dark" : "text-ink2"}
                strokeWidth={active ? 2.4 : 1.9}
              />
              {href === "/checkout" && count > 0 && (
                <span className="absolute -top-1.5 -right-2 min-w-4 h-4 px-1 rounded-full bg-amzn-orange text-white text-[10px] font-bold flex items-center justify-center">
                  {count}
                </span>
              )}
            </span>
            <span className={`text-[10px] font-medium ${active ? "text-amzn-dark" : "text-ink2"}`}>
              {label}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
