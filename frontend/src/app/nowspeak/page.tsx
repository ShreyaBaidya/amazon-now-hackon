"use client";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, Check, ChevronLeft, Clock, Mic, Sparkles ,ShoppingBag} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ProductRow } from "@/components/ProductCard";
import { api } from "@/lib/api";
import { useCart } from "@/lib/cart";
import { rupee } from "@/lib/format";
import { useVoice } from "@/lib/useVoice";
import type { SpeakResult } from "@/lib/types";

type Msg = {
  role: "user" | "assistant";
  text: string;
  result?: SpeakResult;
  streaming?: boolean;
};

export default function NowSpeakPage() {
  const [chips, setChips] = useState<string[]>([]);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const { addMany } = useCart();
  const router = useRouter();
  const voice = useVoice((t) => {
    setInput(t);
    setTimeout(() => send(t), 250);
  });

  useEffect(() => {
    api.speakStarters().then((d) => setChips(d.chips)).catch(() => {});
    return () => esRef.current?.close();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [msgs]);

  const send = (q: string) => {
    const query = q.trim();
    if (!query || busy) return;
    setInput("");
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", text: query }, { role: "assistant", text: "", streaming: true }]);

    const es = new EventSource(api.streamUrl(query));
    esRef.current = es;
    es.addEventListener("token", (e: MessageEvent) => {
      const { t } = JSON.parse(e.data);
      setMsgs((m) => {
        const c = [...m];
        c[c.length - 1] = { ...c[c.length - 1], text: c[c.length - 1].text + t };
        return c;
      });
    });
    es.addEventListener("result", (e: MessageEvent) => {
      const result = JSON.parse(e.data) as SpeakResult;
      setMsgs((m) => {
        const c = [...m];
        c[c.length - 1] = { ...c[c.length - 1], result, streaming: false };
        return c;
      });
    });
    es.addEventListener("done", () => {
      es.close();
      setBusy(false);
    });
    es.onerror = () => {
      es.close();
      setBusy(false);
      setMsgs((m) => {
        const c = [...m];
        c[c.length - 1] = { ...c[c.length - 1], streaming: false };
        return c;
      });
    };
  };

  const addAll = (r: SpeakResult) => {
    addMany(r.products.map((p) => ({ product: p, qty: 1 })));
    router.push("/checkout?src=nowspeak");
  };

  return (
    <div className="flex flex-col h-full">
      {/* header */}
      <header className="bg-amzn-dark text-white px-3 pt-2 pb-3 shrink-0 flex items-center gap-2">
        <button onClick={() => router.push("/")} className="p-1">
          <ChevronLeft size={22} />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-1.5 font-bold">
            <Sparkles size={16} className="text-amzn-yellow" /> NowSpeak
          </div>
          <p className="text-[11px] text-white/60">Describe the situation — skip the search</p>
        </div>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto no-scrollbar px-3 py-3 pb-28">
        {msgs.length === 0 && (
          <div className="mt-6">
            <div className="mx-auto h-16 w-16 rounded-2xl bg-gradient-to-br from-amzn-dark to-amzn-blue2 grid place-items-center">
              <Mic size={28} className="text-amzn-yellow" />
            </div>
            <p className="text-center text-[15px] font-bold mt-3">What do you need?</p>
            <p className="text-center text-[12px] text-ink2 mt-1 px-6">
              Say what to cook, paste a shopping list, or drop a recipe link — I&apos;ll find everything.
            </p>
            <div className="mt-5 space-y-2">
              {chips.map((c) => (
                <button
                  key={c}
                  onClick={() => send(c)}
                  className="w-full text-left bg-white border border-line rounded-2xl px-3.5 py-3 text-[13px] font-medium shadow-card active:scale-[0.98] transition flex items-center gap-2"
                >
                  <span className="text-amzn-orange">“</span>
                  {c}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-3">
          {msgs.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="flex justify-end">
                <div className="bg-amzn-dark text-white rounded-2xl rounded-br-md px-3.5 py-2 text-[13px] max-w-[80%]">
                  {m.text}
                </div>
              </div>
            ) : (
              <div key={i} className="space-y-2">
                <div className="flex gap-2">
                  <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-amzn-dark to-amzn-blue2 grid place-items-center shrink-0">
                    <Sparkles size={14} className="text-amzn-yellow" />
                  </div>
                  <div className="bg-white border border-line rounded-2xl rounded-tl-md px-3.5 py-2.5 text-[13px] leading-relaxed shadow-card">
                    {m.text}
                    {m.streaming && <span className="inline-block w-1.5 h-4 align-middle bg-amzn-dark/60 ml-0.5 animate-pulse" />}
                  </div>
                </div>
                {m.result && <ResultCard result={m.result} onAddAll={() => addAll(m.result!)} />}
              </div>
            ),
          )}
        </div>
      </div>

      {/* input bar */}
      <div className="absolute bottom-16 inset-x-0 z-20 bg-white border-t border-line px-3 py-2.5">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="flex items-center gap-2"
        >
          <div className="flex-1 flex items-center bg-paper rounded-full px-4 h-11">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={voice.listening ? "Listening…" : "Type, paste a list, or drop a link…"}
              className="flex-1 bg-transparent outline-none text-[13px]"
            />
          </div>
          <button
            type="button"
            onClick={voice.toggle}
            className={`h-11 w-11 rounded-full grid place-items-center shrink-0 ${
              voice.listening ? "bg-amzn-red text-white pulse-ring" : "bg-paper text-amzn-dark"
            }`}
          >
            <Mic size={19} />
          </button>
          <button
            type="submit"
            disabled={!input.trim() || busy}
            className="h-11 w-11 rounded-full bg-amzn-yellow2 text-amzn-dark grid place-items-center shrink-0 disabled:opacity-40"
          >
            <ArrowUp size={20} strokeWidth={2.5} />
          </button>
        </form>
      </div>
    </div>
  );
}

function ResultCard({ result, onAddAll }: { result: SpeakResult; onAddAll: () => void }) {
  // Safe validation check to handle both recipe modules and broad event notes
  const hasRecipe = !!result.recipe;
  const lifestyleNote = !hasRecipe && result.note ? result.note : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="ml-9 bg-white border border-line rounded-2xl shadow-card overflow-hidden"
    >
      {/* Header State 1: Image Recipe Card */}
      {hasRecipe && result.recipe && (
        <div className="relative h-28 select-none">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={result.recipe.image} alt="" className="absolute inset-0 h-full w-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent" />
          <div className="absolute bottom-2 left-3 right-3 text-white">
            <p className="font-bold text-[15px] drop-shadow-sm line-clamp-1">{result.recipe.name}</p>
            <p className="text-[11px] text-white/90 flex items-center gap-2 mt-0.5">
              <span className="flex items-center gap-1">
                <Clock size={11} /> {result.recipe.time_min} min
              </span>
              · serves {result.recipe.servings}
            </p>
          </div>
        </div>
      )}

      {/* Header State 2: Adaptive Lifestyle Custom Pack Title */}
      {lifestyleNote && (
        <div className="bg-gradient-to-r from-amzn-dark to-amzn-blue2 px-3.5 py-3.5 text-white relative overflow-hidden select-none">
          <div className="relative z-10 flex flex-col gap-1">
            <span className="text-[9px] w-max uppercase font-bold tracking-wider text-amzn-yellow bg-white/10 px-1.5 py-0.5 rounded">
              Custom Bundle
            </span>
            <p className="font-bold text-[14px] leading-snug line-clamp-2">{lifestyleNote}</p>
          </div>
          <div className="absolute -right-4 -bottom-4 w-20 h-20 bg-white/5 rounded-full blur-xl pointer-events-none" />
        </div>
      )}

      {/* Dietary Note Banner */}
      {result.dietary_note && (
        <div className="bg-amzn-greenlite text-amzn-green text-[12px] font-semibold px-3 py-2 flex items-center gap-1.5 border-b border-line/20">
          <Check size={14} strokeWidth={2.5} className="shrink-0" />
          <span className="truncate">{result.dietary_note}</span>
        </div>
      )}

      {/* Product Row Container */}
      <div className="px-3 divide-y divide-line/60 bg-white">
        {result.products && result.products.length > 0 ? (
          result.products.map((p) => (
            <ProductRow key={p.id} product={p} />
          ))
        ) : (
          <div className="py-4 text-center text-ink2 text-[12px]">No directly matching inventory items found.</div>
        )}
      </div>

      {/* Collective Checkout Action */}
      {result.products && result.products.length > 0 && (
        <button
          onClick={onAddAll}
          className="m-3 w-[calc(100%-1.5rem)] rounded-xl bg-amzn-yellow2 hover:bg-amzn-yellow text-amzn-dark font-bold py-3 text-[14px] flex items-center justify-center gap-2 shadow-sm transition active:scale-[0.99]"
        >
          <ShoppingBag size={15} />
          <span>Add all {result.products.length} · {rupee(result.total)}</span>
        </button>
      )}
    </motion.div>
  );
}