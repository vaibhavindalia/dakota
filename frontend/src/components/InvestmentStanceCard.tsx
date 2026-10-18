"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type StancePillar = {
  name: string;
  status: string;
  score?: number;
  band?: string;
  verdict?: string;
  summary: string;
  pe_ratio?: number;
  revenue_cr?: number;
  debt_cr?: number;
  profit_cr?: number;
  promoter_pct?: number;
};

export type StanceChecklistItem = {
  id: string;
  label: string;
  passed: boolean;
  detail: string;
};

export type InvestmentStanceData = {
  ticker: string;
  stance: "FAVORABLE_SETUP" | "SAFE_DOWNTREND" | "CONSOLIDATING_WATCHLIST" | "SURVEILLANCE_CAUTION" | "CRITICAL_AVOID";
  stance_badge: string;
  theme: "emerald" | "amber" | "sky" | "orange" | "red";
  title: string;
  actionable_guidance: string;
  pillars: {
    forensic: StancePillar;
    technical: StancePillar;
    fundamental: StancePillar;
  };
  checklist: StanceChecklistItem[];
  checklist_passed_count: number;
  checklist_total_count: number;
};

export default function InvestmentStanceCard({
  ticker,
  initialData,
}: {
  ticker: string;
  initialData?: InvestmentStanceData | null;
}) {
  const [data, setData] = useState<InvestmentStanceData | null>(initialData || null);
  const [loading, setLoading] = useState(!initialData);
  const [error, setError] = useState("");
  const [showChecklist, setShowChecklist] = useState(false);

  useEffect(() => {
    if (initialData) {
      setData(initialData);
      setLoading(false);
      return;
    }

    let cancelled = false;
    async function fetchStance() {
      setLoading(true);
      setError("");
      try {
        const res = await fetch(`${API}/api/stocks/${encodeURIComponent(ticker)}/decision`, {
          cache: "no-store",
        });
        if (!res.ok) throw new Error("Could not load investment decision stance");
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Error");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    if (ticker) {
      fetchStance();
    }

    return () => {
      cancelled = true;
    };
  }, [ticker, initialData]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-white/10 bg-gradient-to-b from-zinc-950 to-black p-6 text-center animate-pulse">
        <div className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-sky-400 border-t-transparent mb-2" />
        <p className="text-xs text-zinc-400">Evaluating 3-Pillar Investment Stance (Forensics + Trend + Fundamentals)...</p>
      </div>
    );
  }

  if (error || !data) {
    return null; // Fail silently if not available
  }

  // Theme configuration
  const themeStyles = {
    emerald: {
      border: "border-emerald-500/30",
      bgGradient: "from-emerald-950/40 via-zinc-950 to-black",
      badge: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
      glow: "shadow-[0_0_30px_rgba(16,185,129,0.15)]",
      icon: "🟢",
    },
    amber: {
      border: "border-amber-500/30",
      bgGradient: "from-amber-950/40 via-zinc-950 to-black",
      badge: "bg-amber-500/10 text-amber-400 border-amber-500/30",
      glow: "shadow-[0_0_30px_rgba(245,158,11,0.15)]",
      icon: "🟡",
    },
    sky: {
      border: "border-sky-500/30",
      bgGradient: "from-sky-950/40 via-zinc-950 to-black",
      badge: "bg-sky-500/10 text-sky-400 border-sky-500/30",
      glow: "shadow-[0_0_30px_rgba(14,165,233,0.15)]",
      icon: "🔵",
    },
    orange: {
      border: "border-orange-500/30",
      bgGradient: "from-orange-950/40 via-zinc-950 to-black",
      badge: "bg-orange-500/10 text-orange-400 border-orange-500/30",
      glow: "shadow-[0_0_30px_rgba(249,115,22,0.15)]",
      icon: "🟠",
    },
    red: {
      border: "border-red-500/40",
      bgGradient: "from-red-950/50 via-zinc-950 to-black",
      badge: "bg-red-500/15 text-red-400 border-red-500/40",
      glow: "shadow-[0_0_35px_rgba(239,68,68,0.2)]",
      icon: "🔴",
    },
  }[data.theme] || {
    border: "border-zinc-800",
    bgGradient: "from-zinc-900 to-black",
    badge: "bg-zinc-800 text-zinc-300 border-zinc-700",
    glow: "",
    icon: "⚪",
  };

  const getPillarStatusBadge = (status: string) => {
    switch (status) {
      case "PASS":
      case "BULLISH":
      case "HEALTHY":
        return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
      case "CAUTION":
      case "NEUTRAL":
      case "MODERATE":
        return "bg-sky-500/10 text-sky-400 border-sky-500/20";
      case "BEARISH":
        return "bg-amber-500/10 text-amber-400 border-amber-500/20";
      default:
        return "bg-red-500/10 text-red-400 border-red-500/20";
    }
  };

  return (
    <div
      className={`relative overflow-hidden rounded-2xl border ${themeStyles.border} bg-gradient-to-b ${themeStyles.bgGradient} p-6 lg:p-7 ${themeStyles.glow} transition-all`}
    >
      {/* Top Banner Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-5">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{themeStyles.icon}</span>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                Actionable Investment Stance
              </span>
              <span
                className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide ${themeStyles.badge}`}
              >
                {data.stance_badge}
              </span>
            </div>
            <h2 className="mt-0.5 text-xl font-bold tracking-tight text-white">{data.title}</h2>
          </div>
        </div>

        {/* Due Diligence Checklist Score Counter */}
        <div className="flex items-center gap-3">
          <div className="rounded-xl border border-white/10 bg-black/40 px-3.5 py-2 text-right">
            <div className="text-[10px] uppercase tracking-wider text-zinc-400">Due Diligence Checklist</div>
            <div className="text-sm font-bold text-white">
              <span
                className={
                  data.checklist_passed_count >= 4
                    ? "text-emerald-400"
                    : data.checklist_passed_count >= 3
                    ? "text-amber-400"
                    : "text-red-400"
                }
              >
                {data.checklist_passed_count}
              </span>{" "}
              / {data.checklist_total_count} Passed
            </div>
          </div>
        </div>
      </div>

      {/* Plain Language Actionable Guidance Callout */}
      <div className="my-5 rounded-xl border border-white/10 bg-white/[0.02] p-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 text-sm font-bold text-sky-400">💡</span>
          <div>
            <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wide">Real-World Guidance</div>
            <p className="mt-1 text-sm leading-relaxed text-zinc-300 font-medium">
              {data.actionable_guidance}
            </p>
          </div>
        </div>
      </div>

      {/* 3-Pillar Institutional Assessment Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-1">
        {/* Pillar 1: Forensics */}
        <div className="rounded-xl border border-white/5 bg-black/40 p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
                🛡️ Forensic Shield
              </span>
              <span
                className={`rounded border px-2 py-0.5 text-[11px] font-semibold ${getPillarStatusBadge(
                  data.pillars.forensic.status
                )}`}
              >
                {data.pillars.forensic.status}
              </span>
            </div>
            <div className="mt-2 text-xl font-extrabold text-white">
              {data.pillars.forensic.score?.toFixed(1)}{" "}
              <span className="text-xs font-normal text-zinc-500">Risk Score ({data.pillars.forensic.band})</span>
            </div>
            <p className="mt-2 text-xs text-zinc-400 leading-relaxed">
              {data.pillars.forensic.summary}
            </p>
          </div>
        </div>

        {/* Pillar 2: Technicals */}
        <div className="rounded-xl border border-white/5 bg-black/40 p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
                📈 Trend & Timing
              </span>
              <span
                className={`rounded border px-2 py-0.5 text-[11px] font-semibold ${getPillarStatusBadge(
                  data.pillars.technical.status
                )}`}
              >
                {data.pillars.technical.status}
              </span>
            </div>
            <div className="mt-2 text-xl font-extrabold text-white">
              {data.pillars.technical.verdict || "NEUTRAL"}{" "}
              <span className="text-xs font-normal text-zinc-500">Consensus</span>
            </div>
            <p className="mt-2 text-xs text-zinc-400 leading-relaxed">
              {data.pillars.technical.summary}
            </p>
          </div>
        </div>

        {/* Pillar 3: Fundamentals */}
        <div className="rounded-xl border border-white/5 bg-black/40 p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
                🏛️ Solvency & Health
              </span>
              <span
                className={`rounded border px-2 py-0.5 text-[11px] font-semibold ${getPillarStatusBadge(
                  data.pillars.fundamental.status
                )}`}
              >
                {data.pillars.fundamental.status}
              </span>
            </div>
            <div className="mt-2 text-xl font-extrabold text-white">
              {data.pillars.fundamental.pe_ratio != null
                ? `P/E ${data.pillars.fundamental.pe_ratio.toFixed(1)}`
                : "Institutional"}{" "}
              <span className="text-xs font-normal text-zinc-500">
                {data.pillars.fundamental.profit_cr != null && data.pillars.fundamental.profit_cr > 0
                  ? `(₹${data.pillars.fundamental.profit_cr.toFixed(0)} cr profit)`
                  : "Profile"}
              </span>
            </div>
            <p className="mt-2 text-xs text-zinc-400 leading-relaxed">
              {data.pillars.fundamental.summary}
            </p>
          </div>
        </div>
      </div>

      {/* Expandable 5-Point Due Diligence Checklist */}
      <div className="mt-5 border-t border-white/10 pt-4">
        <button
          onClick={() => setShowChecklist(!showChecklist)}
          className="flex items-center justify-between w-full text-xs font-semibold text-zinc-400 hover:text-white transition py-1"
        >
          <span className="flex items-center gap-2">
            <span>📋</span>
            <span>View 5-Point Real-Life Due Diligence Checklist</span>
          </span>
          <span>{showChecklist ? "▲ Hide Details" : "▼ Expand Checklist"}</span>
        </button>

        {showChecklist && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1 animate-fadeIn">
            {data.checklist.map((item) => (
              <div
                key={item.id}
                className={`rounded-lg border p-3 flex items-start gap-2.5 text-xs ${
                  item.passed
                    ? "border-emerald-500/20 bg-emerald-950/20 text-emerald-200"
                    : "border-red-500/20 bg-red-950/20 text-red-200"
                }`}
              >
                <span className="mt-0.5 font-bold">{item.passed ? "✓" : "✗"}</span>
                <div>
                  <div className="font-semibold text-white">{item.label}</div>
                  <div className="mt-0.5 text-[11px] text-zinc-400">{item.detail}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
