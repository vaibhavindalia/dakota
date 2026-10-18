"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import {
  Eye,
  ShieldAlert,
  AlertTriangle,
  Activity,
  Radar,
  Zap,
  Clock,
  ArrowUpRight,
  ShieldCheck,
  Layers,
  Radio,
  RefreshCw,
} from "lucide-react";

type Risk = {
  score?: number;
  band?: string;
  verdict?: string;
  as_of?: string;
  reasons?: string[];
  next_steps?: string[];
  contributions?: Record<string, number>;
  contribution_labels?: Record<string, string>;
};

type Holding = {
  ticker: string;
  name: string;
  exchange: string;
  quantity: number;
  average_buy_price: number | null;
  risk?: Risk | null;
};

type Portfolio = {
  name: string;
  holdings: Holding[];
};

type WatchEvent = {
  ticker: string;
  name: string;
  score: number | null;
  band: string;
  reason: string;
};

export default function WatcherPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastRefreshed, setLastRefreshed] = useState<string>("");

  async function loadWatcher() {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/portfolio`,
        {
          cache: "no-store",
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail || "Could not load Watcher data.");
      }

      setPortfolio(data);
      setLastRefreshed(new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load Watcher data."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadWatcher();
  }, []);

  const events = useMemo<WatchEvent[]>(() => {
    if (!portfolio) {
      return [];
    }

    const output: WatchEvent[] = [];

    for (const holding of portfolio.holdings) {
      const risk = holding.risk;

      if (!risk) {
        continue;
      }

      const reasons = risk.reasons ?? [];

      for (const reason of reasons.slice(0, 4)) {
        output.push({
          ticker: holding.ticker,
          name: holding.name,
          score: typeof risk.score === "number" ? risk.score : null,
          band: risk.band ?? "Unknown",
          reason,
        });
      }
    }

    return output;
  }, [portfolio]);

  function riskClass(band?: string) {
    if (band === "High") {
      return "border-rose-500/40 bg-rose-950/40 text-rose-300";
    }

    if (band === "Elevated") {
      return "border-amber-500/40 bg-amber-950/40 text-amber-300";
    }

    if (band === "Low") {
      return "border-emerald-500/40 bg-emerald-950/40 text-emerald-300";
    }

    return "border-zinc-800 bg-zinc-900/60 text-zinc-400";
  }

  const highRiskCount =
    portfolio?.holdings.filter((h) => h.risk?.band === "High").length ?? 0;

  const elevatedCount =
    portfolio?.holdings.filter((h) => h.risk?.band === "Elevated").length ?? 0;

  const safeCount =
    portfolio?.holdings.filter((h) => h.risk?.band === "Low").length ?? 0;

  return (
    <main className="min-h-screen bg-[#05070a] text-zinc-100 bg-terminal-grid">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <Navbar />

        {/* Institutional Surveillance Header */}
        <header className="relative mb-8 mt-6 overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-r from-zinc-950 via-[#070d18] to-zinc-950 p-6 md:p-8 shadow-2xl">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-0.5 text-xs font-semibold tracking-wider text-sky-400 uppercase">
                  <Radar className="h-3.5 w-3.5 animate-spin" /> Live Sentinel
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-0.5 text-xs font-semibold tracking-wider text-emerald-400 uppercase">
                  <Radio className="h-3 w-3 animate-pulse" /> Surveillance Engine Active
                </span>
                {lastRefreshed && (
                  <span className="flex items-center gap-1 text-xs text-zinc-500">
                    <Clock className="h-3 w-3" /> Updated {lastRefreshed} IST
                  </span>
                )}
              </div>

              <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-white md:text-4xl flex items-center gap-3">
                Portfolio Watcher
                <span className="text-sm font-normal text-zinc-500 bg-zinc-900 border border-zinc-800 px-3 py-1 rounded-lg">
                  Scrip Sentinel
                </span>
              </h1>

              <p className="mt-2 max-w-2xl text-sm text-zinc-400 leading-relaxed">
                Autonomous real-time surveillance over your invested holdings. Dakota cross-references SEBI regulatory circulars, ASM/GSM surveillance lists, operator pump signatures, and volume divergence patterns.
              </p>
            </div>

            <div className="flex items-center gap-3 self-start md:self-auto">
              <button
                onClick={loadWatcher}
                disabled={loading}
                className="flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/80 px-4 py-2.5 text-xs font-semibold text-zinc-300 transition hover:bg-zinc-800 hover:text-white disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                Refresh Sentinel
              </button>
              <Link
                href="/portfolio"
                className="flex items-center gap-1.5 rounded-xl border border-sky-500/40 bg-sky-500/10 px-4 py-2.5 text-xs font-semibold text-sky-300 transition hover:bg-sky-500/20"
              >
                Manage Portfolio <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>
        </header>

        {error && (
          <div className="mb-8 rounded-2xl border border-rose-500/30 bg-rose-950/30 p-5 text-sm text-rose-300 flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="rounded-2xl border border-white/5 bg-zinc-950/80 p-12 text-center">
            <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-sky-400 border-t-transparent mb-3" />
            <p className="text-sm text-zinc-400">Scanning portfolio scrips against active risk patterns...</p>
          </div>
        ) : (
          <>
            {/* Surveillance KPI Grid */}
            <section className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
              <div className="rounded-2xl border border-zinc-800/80 bg-zinc-950/60 p-5 shadow-lg relative overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-sky-500 to-cyan-500" />
                <div className="flex items-center justify-between text-xs text-zinc-500 font-semibold uppercase tracking-wider">
                  <span>Monitored Scrips</span>
                  <Eye className="h-4 w-4 text-sky-400" />
                </div>
                <div className="mt-3 text-3xl font-extrabold text-white tabular-nums">
                  {portfolio?.holdings.length ?? 0}
                </div>
                <div className="mt-1 text-xs text-zinc-500">Active holdings under surveillance</div>
              </div>

              <div className="rounded-2xl border border-rose-500/20 bg-rose-950/10 p-5 shadow-lg relative overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-1 bg-rose-500" />
                <div className="flex items-center justify-between text-xs text-rose-400 font-semibold uppercase tracking-wider">
                  <span>High Risk Scrips</span>
                  <ShieldAlert className="h-4 w-4 text-rose-400" />
                </div>
                <div className="mt-3 text-3xl font-extrabold text-rose-400 tabular-nums">
                  {highRiskCount}
                </div>
                <div className="mt-1 text-xs text-rose-400/70">Critical forensic anomalies flagged</div>
              </div>

              <div className="rounded-2xl border border-amber-500/20 bg-amber-950/10 p-5 shadow-lg relative overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-1 bg-amber-500" />
                <div className="flex items-center justify-between text-xs text-amber-400 font-semibold uppercase tracking-wider">
                  <span>Elevated Caution</span>
                  <AlertTriangle className="h-4 w-4 text-amber-400" />
                </div>
                <div className="mt-3 text-3xl font-extrabold text-amber-400 tabular-nums">
                  {elevatedCount}
                </div>
                <div className="mt-1 text-xs text-amber-400/70">Warrants active stop-loss scrutiny</div>
              </div>

              <div className="rounded-2xl border border-emerald-500/20 bg-emerald-950/10 p-5 shadow-lg relative overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-1 bg-emerald-500" />
                <div className="flex items-center justify-between text-xs text-emerald-400 font-semibold uppercase tracking-wider">
                  <span>Surveillance Alerts</span>
                  <Activity className="h-4 w-4 text-emerald-400" />
                </div>
                <div className="mt-3 text-3xl font-extrabold text-emerald-400 tabular-nums">
                  {events.length}
                </div>
                <div className="mt-1 text-xs text-emerald-400/70">Total individual signal triggers</div>
              </div>
            </section>

            {/* Holdings Surveillance Cards */}
            <section className="mb-10">
              <div className="mb-5 flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <Layers className="h-5 w-5 text-sky-400" /> Portfolio Health Inspection
                  </h2>
                  <p className="mt-0.5 text-xs text-zinc-500">
                    Live risk breakdown and forensic signals per holding.
                  </p>
                </div>
              </div>

              {portfolio?.holdings.length === 0 ? (
                <div className="rounded-2xl border border-zinc-800 bg-zinc-950/80 p-12 text-center">
                  <ShieldCheck className="mx-auto h-12 w-12 text-zinc-600 mb-3" />
                  <p className="text-base font-semibold text-zinc-300">Your portfolio is currently empty</p>
                  <p className="mt-1 text-xs text-zinc-500 max-w-sm mx-auto">
                    Add NSE/BSE holdings to start the automated forensic surveillance watcher.
                  </p>
                  <Link
                    href="/portfolio"
                    className="mt-4 inline-flex items-center gap-2 rounded-xl bg-sky-500 px-4 py-2 text-xs font-semibold text-black transition hover:bg-sky-400"
                  >
                    Add Holdings to Portfolio
                  </Link>
                </div>
              ) : (
                <div className="grid gap-5 lg:grid-cols-2">
                  {portfolio?.holdings.map((holding) => {
                    const risk = holding.risk;
                    const score = risk?.score;
                    const isHigh = risk?.band === "High";
                    const isElevated = risk?.band === "Elevated";

                    return (
                      <article
                        key={holding.ticker}
                        className={`rounded-2xl border transition hover:border-zinc-700 p-6 ${
                          isHigh
                            ? "border-rose-500/30 bg-rose-950/10"
                            : isElevated
                            ? "border-amber-500/30 bg-amber-950/10"
                            : "border-zinc-800 bg-zinc-950/60"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-2xl font-black tracking-tight text-white">
                                {holding.ticker}
                              </span>
                              <Link
                                href={`/stocks?search=${encodeURIComponent(holding.ticker)}`}
                                className="rounded-lg p-1 text-zinc-500 hover:bg-zinc-800 hover:text-sky-400 transition"
                                title="Open in Terminal Screener"
                              >
                                <ArrowUpRight className="h-4 w-4" />
                              </Link>
                            </div>

                            <p className="mt-0.5 text-xs font-medium text-zinc-400">
                              {holding.name}
                            </p>

                            <div className="mt-2 flex items-center gap-2 text-[11px] text-zinc-500">
                              <span className="rounded bg-zinc-900 px-1.5 py-0.5 font-mono text-zinc-400">
                                {holding.exchange}
                              </span>
                              <span>•</span>
                              <span>{holding.quantity} shares</span>
                              {holding.average_buy_price && (
                                <>
                                  <span>•</span>
                                  <span>Avg ₹{holding.average_buy_price.toLocaleString("en-IN")}</span>
                                </>
                              )}
                            </div>
                          </div>

                          <div className="text-right">
                            <div className="flex items-baseline justify-end gap-1 font-mono text-3xl font-black">
                              <span
                                className={
                                  isHigh
                                    ? "text-rose-400"
                                    : isElevated
                                    ? "text-amber-400"
                                    : "text-emerald-400"
                                }
                              >
                                {score ?? "—"}
                              </span>
                              {score != null && (
                                <span className="text-xs text-zinc-600 font-normal">/100</span>
                              )}
                            </div>

                            <span
                              className={`mt-1.5 inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${riskClass(
                                risk?.band
                              )}`}
                            >
                              {risk?.band ?? "No Data"}
                            </span>
                          </div>
                        </div>

                        {/* Assessment Verdict */}
                        <div className="mt-4 rounded-xl border border-white/5 bg-black/40 p-3.5">
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                            Surveillance Verdict
                          </p>
                          <p className="mt-1 text-xs text-zinc-300 leading-relaxed">
                            {risk?.verdict ?? "No risk assessment available for this scrip."}
                          </p>
                        </div>

                        {/* Signal Triggers */}
                        <div className="mt-4">
                          <p className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                            Active Flagged Triggers
                          </p>

                          {risk?.reasons && risk.reasons.length > 0 ? (
                            <div className="mt-2.5 space-y-1.5">
                              {risk.reasons.slice(0, 4).map((reason, index) => (
                                <div
                                  key={`${reason}-${index}`}
                                  className="flex items-start gap-2 rounded-lg border border-white/5 bg-zinc-900/40 px-3 py-2 text-xs text-zinc-300"
                                >
                                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-400" />
                                  <span className="leading-snug">{reason}</span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="mt-2 text-xs text-zinc-600">
                              No active forensic flags triggered for this scrip.
                            </p>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </section>

            {/* Live Intelligence Feed */}
            <section className="mb-12">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <Radio className="h-5 w-5 text-emerald-400" /> Live Surveillance Intelligence Feed
                  </h2>
                  <p className="mt-0.5 text-xs text-zinc-500">
                    Chronological chronological alert stream extracted from portfolio scrips.
                  </p>
                </div>
                <span className="text-xs font-mono text-zinc-500">
                  {events.length} Signal Triggers
                </span>
              </div>

              <div className="overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950/60 shadow-xl">
                {events.length === 0 ? (
                  <div className="p-10 text-center text-xs text-zinc-500">
                    No signals currently recorded. Watcher is monitoring background feeds.
                  </div>
                ) : (
                  <div className="divide-y divide-zinc-900">
                    {events.map((event, index) => (
                      <div
                        key={`${event.ticker}-${index}`}
                        className="flex flex-col gap-3 p-4.5 transition hover:bg-zinc-900/30 sm:flex-row sm:items-center sm:justify-between px-5 py-4"
                      >
                        <div className="flex items-start gap-3">
                          <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-sky-400" />
                          <div>
                            <div className="flex items-center gap-2.5">
                              <span className="font-mono font-bold text-sm text-white">
                                {event.ticker}
                              </span>
                              <span
                                className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${riskClass(
                                  event.band
                                )}`}
                              >
                                {event.band}
                              </span>
                              <span className="text-xs text-zinc-500 truncate max-w-xs">
                                {event.name}
                              </span>
                            </div>

                            <p className="mt-1 text-xs text-zinc-300">
                              {event.reason}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-4 self-end sm:self-auto shrink-0">
                          <span className="font-mono text-xs text-zinc-500">
                            Risk {event.score ?? "—"}/100
                          </span>
                          <Link
                            href={`/stocks?search=${encodeURIComponent(event.ticker)}`}
                            className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-1 text-[11px] font-medium text-zinc-300 transition hover:bg-zinc-800 hover:text-white"
                          >
                            Inspect <ArrowUpRight className="h-3 w-3" />
                          </Link>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          </>
        )}

        <footer className="mt-16 border-t border-zinc-900 pt-6 pb-8 text-center text-xs text-zinc-600 flex flex-col sm:flex-row items-center justify-between gap-4">
          <span>Dakota Financial Intelligence Terminal • Portfolio Watcher</span>
          <span className="font-mono text-[11px] text-zinc-500">NSE / BSE Surveillance Feed v2.4</span>
        </footer>
      </div>
    </main>
  );
}