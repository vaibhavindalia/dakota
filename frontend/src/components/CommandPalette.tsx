"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { 
  Search, 
  TrendingUp, 
  ShieldAlert, 
  Briefcase, 
  Radio, 
  Users, 
  Eye, 
  X,
  Sparkles,
  ArrowRight,
  Activity,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type SearchStock = {
  ticker: string;
  name: string;
  exchange: string;
  segment: string;
  score: number | null;
  band: string;
};

const QUICK_ACTIONS = [
  { label: "Dakota AI Copilot", href: "/intelligence", icon: Sparkles, desc: "Grounded investigative AI assistant & intelligence reports" },
  { label: "QN Surveillance", href: "/surveillance", icon: Activity, desc: "Quantitative manipulation pipeline & 500-stock benchmark" },
  { label: "Equities Screener", href: "/stocks", icon: TrendingUp, desc: "Search 2,615+ Indian stocks and indicators" },
  { label: "Tip Forensic Analyzer", href: "/", icon: ShieldAlert, desc: "Analyze WhatsApp/Telegram stock tips for fraud" },
  { label: "Portfolio Intelligence", href: "/portfolio", icon: Briefcase, desc: "Track portfolio holdings and forensic risk" },
  { label: "Live Forensic Wire", href: "/investigate", icon: Radio, desc: "Multi-source live intelligence feed" },
  { label: "Syndicate Campaigns", href: "/campaigns", icon: Users, desc: "Track coordinated promoter and channel cartels" },
  { label: "Surveillance Watcher", href: "/watcher", icon: Eye, desc: "Real-time alerts on high-risk securities" },
];

export default function CommandPalette({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchStock[]>([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setQuery("");
      setResults([]);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${API}/api/stocks?search=${encodeURIComponent(query.trim())}&limit=8`);
        if (res.ok) {
          const data = await res.json();
          const items = Array.isArray(data) ? data : data.stocks || [];
          setResults(items);
        }
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [query]);

  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 z-[100] flex items-start justify-center pt-20 px-4 bg-black/80 backdrop-blur-md"
      onClick={onClose}
    >
      <div 
        className="w-full max-w-2xl rounded-2xl border border-white/15 bg-[#0a0e17] shadow-2xl overflow-hidden ring-1 ring-cyan-500/20"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-white/10 bg-white/[0.02]">
          <Search className="w-5 h-5 text-cyan-400 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search stock ticker (e.g. ZOMATO, RELIANCE, BASILIC)..."
            className="w-full bg-transparent text-sm text-white placeholder-slate-500 outline-none font-medium"
          />
          {query && (
            <button 
              onClick={() => setQuery("")}
              className="p-1 text-slate-500 hover:text-white rounded-md"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <span className="hidden sm:inline-flex items-center gap-1 rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
            ESC
          </span>
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-3 space-y-4">
          {query.trim() && (
            <div>
              <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                <span>Stock Equities</span>
                {loading && <span className="text-cyan-400 animate-pulse text-[10px]">Searching 2,615 equities...</span>}
              </div>

              {results.length > 0 ? (
                <div className="mt-1 space-y-1">
                  {results.map((stock) => (
                    <button
                      key={stock.ticker}
                      onClick={() => {
                        onClose();
                        router.push(`/stocks/${stock.ticker}`);
                      }}
                      className="w-full flex items-center justify-between p-2.5 rounded-xl border border-transparent hover:border-cyan-500/30 hover:bg-white/[0.04] transition text-left group"
                    >
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center font-mono font-bold text-xs text-cyan-300">
                          {stock.ticker.slice(0, 3)}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-sm text-white group-hover:text-cyan-300 transition">
                              {stock.ticker}
                            </span>
                            <span className="text-[10px] px-1.5 py-0.2 rounded bg-white/10 font-mono text-slate-400">
                              {stock.exchange || "NSE"}
                            </span>
                            {stock.segment === "surveillance" && (
                              <span className="text-[9px] px-1.5 py-0.2 rounded bg-red-500/20 text-red-300 border border-red-500/30 font-semibold">
                                ASM/GSM
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-slate-400 truncate max-w-sm">
                            {stock.name}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        {stock.score !== null && stock.score !== undefined && (
                          <div className={`text-xs px-2 py-0.5 rounded-md font-mono font-bold border ${
                            stock.band === "High" 
                              ? "border-red-500/30 bg-red-500/10 text-red-400"
                              : stock.band === "Elevated"
                              ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
                              : "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                          }`}>
                            Score {stock.score}/100
                          </div>
                        )}
                        <ArrowRight className="w-4 h-4 text-slate-600 group-hover:text-cyan-400 group-hover:translate-x-0.5 transition" />
                      </div>
                    </button>
                  ))}
                </div>
              ) : !loading ? (
                <div className="p-4 text-center text-xs text-slate-500">
                  No stocks found matching &quot;{query}&quot;. Try searching by NSE ticker or name.
                </div>
              ) : null}
            </div>
          )}

          <div>
            <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Terminal Workspaces
            </div>
            <div className="mt-1 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {QUICK_ACTIONS.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.href}
                    onClick={() => {
                      onClose();
                      router.push(item.href);
                    }}
                    className="flex items-center gap-3 p-2.5 rounded-xl border border-white/5 hover:border-white/15 bg-white/[0.02] hover:bg-white/[0.05] transition text-left group"
                  >
                    <div className="p-2 rounded-lg bg-white/5 text-slate-400 group-hover:text-white group-hover:bg-cyan-500/10 transition">
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-slate-200 group-hover:text-white transition">
                        {item.label}
                      </div>
                      <div className="text-[11px] text-slate-500 truncate">
                        {item.desc}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="px-4 py-2.5 bg-black/40 border-t border-white/10 flex items-center justify-between text-[11px] text-slate-500">
          <div className="flex items-center gap-3">
            <span>Close: <kbd className="font-mono text-slate-400">ESC</kbd></span>
          </div>
          <div className="flex items-center gap-1.5 text-cyan-400/80">
            <Sparkles className="w-3 h-3" />
            <span>Dakota Intelligence Core v0.4</span>
          </div>
        </div>
      </div>
    </div>
  );
}