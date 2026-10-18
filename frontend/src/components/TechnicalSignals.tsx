"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type IndicatorItem = {
  name: string;
  label: string;
  value: number;
  action: "BUY" | "SELL" | "NEUTRAL";
  detail: string;
};

type TechnicalData = {
  ticker: string;
  status: string;
  current_price: number;
  verdict: "STRONG BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG SELL";
  score: number;
  counts: {
    buy: number;
    neutral: number;
    sell: number;
    total: number;
  };
  moving_averages: {
    verdict: string;
    counts: { buy: number; neutral: number; sell: number };
    indicators: IndicatorItem[];
  };
  oscillators: {
    verdict: string;
    counts: { buy: number; neutral: number; sell: number };
    indicators: IndicatorItem[];
  };
  divergence?: {
    divergence_risk: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
    technical_verdict: string;
    technical_score: number;
    rationale: string;
  };
  summary_text: string;
};

export default function TechnicalSignals({
  ticker,
  tipMarkers = 0,
}: {
  ticker: string;
  tipMarkers?: number;
}) {
  const [data, setData] = useState<TechnicalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"all" | "ma" | "osc">("all");

  useEffect(() => {
    let cancelled = false;

    async function fetchTechnicals() {
      setLoading(true);
      setError("");
      try {
        const res = await fetch(
          `${API}/api/stocks/${encodeURIComponent(ticker)}/technicals?tip_markers=${tipMarkers}`,
          { cache: "no-store" }
        );
        if (!res.ok) throw new Error("Could not load technical indicator data");
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Error");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    if (ticker) {
      fetchTechnicals();
    }

    return () => {
      cancelled = true;
    };
  }, [ticker, tipMarkers]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-white/10 bg-[#070b14] p-6 text-center">
        <div className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-sky-400 border-t-transparent mb-2" />
        <p className="text-xs text-white/50">Analyzing technical indicators for {ticker}...</p>
      </div>
    );
  }

  if (error || !data || data.status === "insufficient_data") {
    return (
      <div className="rounded-2xl border border-white/10 bg-[#070b14] p-6 text-xs text-white/40 text-center">
        {error || "Insufficient technical indicator history available for this scrip."}
      </div>
    );
  }

  function getVerdictTheme(verdict: string) {
    switch (verdict) {
      case "STRONG BUY":
        return {
          badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
          glow: "from-emerald-500/20 to-transparent",
          text: "text-emerald-400",
          dot: "bg-emerald-400",
        };
      case "BUY":
        return {
          badge: "bg-teal-500/20 text-teal-300 border-teal-500/40",
          glow: "from-teal-500/20 to-transparent",
          text: "text-teal-400",
          dot: "bg-teal-400",
        };
      case "STRONG SELL":
        return {
          badge: "bg-rose-500/20 text-rose-300 border-rose-500/40",
          glow: "from-rose-500/20 to-transparent",
          text: "text-rose-400",
          dot: "bg-rose-400",
        };
      case "SELL":
        return {
          badge: "bg-amber-500/20 text-amber-300 border-amber-500/40",
          glow: "from-amber-500/20 to-transparent",
          text: "text-amber-400",
          dot: "bg-amber-400",
        };
      default:
        return {
          badge: "bg-zinc-500/20 text-zinc-300 border-zinc-500/40",
          glow: "from-zinc-500/10 to-transparent",
          text: "text-zinc-400",
          dot: "bg-zinc-400",
        };
    }
  }

  function actionBadgeClass(action: "BUY" | "SELL" | "NEUTRAL") {
    if (action === "BUY") return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    if (action === "SELL") return "bg-rose-500/15 text-rose-400 border-rose-500/30";
    return "bg-white/5 text-white/50 border-white/10";
  }

  const theme = getVerdictTheme(data.verdict);
  const segments = ["STRONG SELL", "SELL", "NEUTRAL", "BUY", "STRONG BUY"] as const;

  const allIndicators = [
    ...data.oscillators.indicators,
    ...data.moving_averages.indicators,
  ];

  const displayedIndicators =
    activeTab === "ma"
      ? data.moving_averages.indicators
      : activeTab === "osc"
      ? data.oscillators.indicators
      : allIndicators;

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-[#070b14] p-6 shadow-2xl backdrop-blur-xl">
      {/* Top Header & TradingView-style Meter */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase tracking-[0.2em] text-sky-400 font-semibold">
              TradingView Technical Consensus
            </span>
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          </div>
          <h3 className="mt-1 text-2xl font-bold text-white flex items-center gap-3">
            {data.ticker}
            <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-0.5 text-xs font-bold ${theme.badge}`}>
              <span className={`h-2 w-2 rounded-full ${theme.dot}`} />
              {data.verdict}
            </span>
          </h3>
          <p className="mt-1 text-xs text-white/40">
            {data.counts.buy} Buy · {data.counts.neutral} Neutral · {data.counts.sell} Sell (Total {data.counts.total} Technical Indicators)
          </p>
        </div>

        {/* Segmented Meter Bar */}
        <div className="min-w-[260px] max-w-sm flex-1">
          <div className="text-[10px] uppercase tracking-wider text-white/40 text-right mb-1.5">
            Technical Momentum Gauge
          </div>
          <div className="grid grid-cols-5 gap-1.5">
            {segments.map((seg) => {
              const isActive = data.verdict === seg;
              let barColor = "bg-white/10";
              if (seg === "STRONG SELL") barColor = isActive ? "bg-rose-500 shadow-rose-500/50 shadow-md ring-2 ring-rose-400" : "bg-rose-500/25";
              if (seg === "SELL") barColor = isActive ? "bg-amber-500 shadow-amber-500/50 shadow-md ring-2 ring-amber-400" : "bg-amber-500/25";
              if (seg === "NEUTRAL") barColor = isActive ? "bg-zinc-300 shadow-zinc-300/50 shadow-md ring-2 ring-white" : "bg-zinc-600/25";
              if (seg === "BUY") barColor = isActive ? "bg-teal-500 shadow-teal-500/50 shadow-md ring-2 ring-teal-400" : "bg-teal-500/25";
              if (seg === "STRONG BUY") barColor = isActive ? "bg-emerald-500 shadow-emerald-500/50 shadow-md ring-2 ring-emerald-400" : "bg-emerald-500/25";

              return (
                <div key={seg} className="flex flex-col items-center">
                  <div className={`h-2.5 w-full rounded-sm transition-all duration-300 ${barColor}`} />
                  <span className={`mt-1 text-[8px] font-semibold tracking-tighter ${isActive ? "text-white" : "text-white/30"}`}>
                    {seg.replace("STRONG ", "S.")}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Cluster Summary Row */}
      <div className="my-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Oscillators Summary */}
        <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-white/70 uppercase tracking-wider">Oscillators</span>
            <span className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] font-semibold text-white/90">
              {data.oscillators.verdict}
            </span>
          </div>
          <div className="mt-3 flex gap-4 text-xs">
            <div><strong className="text-emerald-400">{data.oscillators.counts.buy}</strong> <span className="text-white/40">Buy</span></div>
            <div><strong className="text-zinc-300">{data.oscillators.counts.neutral}</strong> <span className="text-white/40">Neutral</span></div>
            <div><strong className="text-rose-400">{data.oscillators.counts.sell}</strong> <span className="text-white/40">Sell</span></div>
          </div>
        </div>

        {/* Moving Averages Summary */}
        <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-white/70 uppercase tracking-wider">Moving Averages</span>
            <span className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] font-semibold text-white/90">
              {data.moving_averages.verdict}
            </span>
          </div>
          <div className="mt-3 flex gap-4 text-xs">
            <div><strong className="text-emerald-400">{data.moving_averages.counts.buy}</strong> <span className="text-white/40">Buy</span></div>
            <div><strong className="text-zinc-300">{data.moving_averages.counts.neutral}</strong> <span className="text-white/40">Neutral</span></div>
            <div><strong className="text-rose-400">{data.moving_averages.counts.sell}</strong> <span className="text-white/40">Sell</span></div>
          </div>
        </div>
      </div>

      {/* Dakota Scam Tip vs Technical Reality Check */}
      {data.divergence && data.divergence.divergence_risk !== "LOW" && (
        <div className={`mb-5 rounded-xl border p-4 text-xs ${
          data.divergence.divergence_risk === "CRITICAL"
            ? "border-rose-500/40 bg-rose-500/10 text-rose-200"
            : "border-amber-500/40 bg-amber-500/10 text-amber-200"
        }`}>
          <div className="flex items-center gap-2 font-bold uppercase tracking-wider mb-1">
            <span>⚠️ Technical vs. Tip Divergence: {data.divergence.divergence_risk} RISK</span>
          </div>
          <p className="opacity-90 leading-relaxed">{data.divergence.rationale}</p>
        </div>
      )}

      {/* Tab Filter Header */}
      <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-4">
        <div className="text-xs font-semibold uppercase tracking-wider text-white/50">
          Indicator Breakdown ({displayedIndicators.length})
        </div>
        <div className="flex gap-1 rounded-lg border border-white/10 bg-white/[0.02] p-0.5">
          <button
            onClick={() => setActiveTab("all")}
            className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
              activeTab === "all" ? "bg-white/15 text-white" : "text-white/40 hover:text-white"
            }`}
          >
            All
          </button>
          <button
            onClick={() => setActiveTab("osc")}
            className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
              activeTab === "osc" ? "bg-white/15 text-white" : "text-white/40 hover:text-white"
            }`}
          >
            Oscillators
          </button>
          <button
            onClick={() => setActiveTab("ma")}
            className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
              activeTab === "ma" ? "bg-white/15 text-white" : "text-white/40 hover:text-white"
            }`}
          >
            Moving Averages
          </button>
        </div>
      </div>

      {/* Indicator List / Table */}
      <div className="max-h-72 overflow-y-auto space-y-2 pr-1">
        {displayedIndicators.map((ind, i) => (
          <div
            key={i}
            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/5 bg-white/[0.015] p-3 text-xs transition hover:bg-white/[0.035]"
          >
            <div className="min-w-[140px]">
              <div className="font-semibold text-white/90">{ind.name}</div>
              <div className="text-[10px] text-white/40">{ind.label}</div>
            </div>

            <div className="text-right">
              <div className="font-mono text-white/90 font-medium">₹{ind.value.toFixed(2)}</div>
            </div>

            <div className="flex-1 min-w-[180px] text-[11px] text-white/60">
              {ind.detail}
            </div>

            <div>
              <span className={`inline-block rounded-md border px-2.5 py-0.5 text-[10px] font-bold ${actionBadgeClass(ind.action)}`}>
                {ind.action}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
