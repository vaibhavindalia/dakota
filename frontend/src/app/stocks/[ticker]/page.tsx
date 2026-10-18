"use client";

import { Suspense, useEffect, useState, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import StockChart from "@/components/StockChart";
import TechnicalSignals from "@/components/TechnicalSignals";
import InvestmentStanceCard, { InvestmentStanceData } from "@/components/InvestmentStanceCard";
import RiskRing from "@/components/RiskRing";
import {
  ArrowLeft,
  ExternalLink,
  ShieldAlert,
  TrendingUp,
  Layers,
  PieChart,
  Calendar,
  Building2,
  Percent,
  ChevronRight,
  Radio,
  Briefcase,
  RefreshCw,
  Clock,
  Activity,
  History,
  CheckCircle2,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type RiskHistoryEntry = {
  id?: number;
  ticker: string;
  score: number;
  band: string;
  verdict?: string;
  calculated_at: string;
  market_data_as_of?: string;
  data_freshness?: string;
  score_change?: number;
  change_reason?: string;
  contributions?: Record<string, number>;
  reasons?: string[];
};

export type StockDetail = {
  ticker: string;
  name?: string;
  exchange?: string;
  segment?: string;
  role?: string;
  latest_price?: number;
  change_pct?: number;
  meta: {
    name?: string;
    exchange?: string;
    segment?: string;
    role?: string;
    listing_date?: string;
    issue_size_cr?: number | string;
    free_float_pct?: number | string;
    notes?: string;
  };
  risk: {
    score?: number | null;
    band?: string;
    verdict?: string;
    reasons?: string[];
    contributions?: Record<string, number>;
    contribution_labels?: Record<string, string>;
    weights?: Record<string, number>;
    calculated_at?: string;
    market_data_as_of?: string;
    data_freshness?: string;
    previous_score?: number | null;
    score_change?: number;
    change_reason?: string;
  };
  decision?: InvestmentStanceData | null;
};

function formatIsoTime(isoStr?: string | null): string {
  if (!isoStr) return "Just now";
  try {
    const dt = new Date(isoStr);
    if (isNaN(dt.getTime())) return isoStr;
    return dt.toLocaleTimeString("en-IN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: true,
    }) + " IST";
  } catch {
    return isoStr;
  }
}

function StockDetailContent() {
  const params = useParams();
  const tickerParam = (Array.isArray(params?.ticker) ? params.ticker[0] : params?.ticker) || "";
  const ticker = tickerParam.toUpperCase();

  const [detail, setDetail] = useState<StockDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Live Auto-Sync State
  const [autoSync, setAutoSync] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [countdown, setCountdown] = useState(15);
  const [scoreFlash, setScoreFlash] = useState<"up" | "down" | null>(null);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [historyList, setHistoryList] = useState<RiskHistoryEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const prevScoreRef = useRef<number | null>(null);
  const inFlightRef = useRef(false);

  // Initial Full Load
  useEffect(() => {
    let active = true;

    async function loadStockDetail() {
      if (!ticker) return;
      setLoading(true);
      setError("");
      try {
        const res = await fetch(`${API}/api/stocks/${encodeURIComponent(ticker)}`, {
          cache: "no-store",
        });
        if (!res.ok) {
          throw new Error(`Failed to load stock data (HTTP ${res.status})`);
        }
        const data = await res.json();
        if (active) {
          setDetail(data);
          prevScoreRef.current = data?.risk?.score ?? null;
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Error loading stock");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadStockDetail();
    return () => {
      active = false;
    };
  }, [ticker]);

  // Synchronized Live Risk Recalculation Function
  const syncRiskScore = useCallback(
    async (force = false) => {
      if (!ticker || inFlightRef.current) return;
      inFlightRef.current = true;
      setSyncing(true);

      try {
        const url = `${API}/api/stocks/${encodeURIComponent(ticker)}/risk${
          force ? "?force_refresh=true" : ""
        }`;
        const res = await fetch(url, { cache: "no-store" });

        if (res.ok) {
          const freshRisk = await res.json();

          setDetail((prev) => {
            if (!prev) return prev;

            const oldScore = prev.risk?.score ?? null;
            const newScore = freshRisk.score ?? null;

            // Trigger score flash animation if score changed
            if (oldScore !== null && newScore !== null && oldScore !== newScore) {
              setScoreFlash(newScore > oldScore ? "up" : "down");
              setTimeout(() => setScoreFlash(null), 1400);

              setSyncNotice(
                `Risk score updated from ${oldScore} → ${newScore} (${
                  freshRisk.change_reason || "Dynamic market updates"
                })`
              );
              setTimeout(() => setSyncNotice(null), 6000);
            }

            prevScoreRef.current = newScore;

            return {
              ...prev,
              risk: {
                ...prev.risk,
                score: freshRisk.score,
                band: freshRisk.band,
                verdict: freshRisk.verdict,
                reasons: freshRisk.reasons,
                contributions: freshRisk.contributions,
                contribution_labels: freshRisk.contribution_labels || prev.risk.contribution_labels,
                weights: freshRisk.weights || prev.risk.weights,
                calculated_at: freshRisk.calculated_at,
                market_data_as_of: freshRisk.market_data_as_of,
                data_freshness: freshRisk.data_freshness,
                previous_score: freshRisk.previous_score,
                score_change: freshRisk.score_change,
                change_reason: freshRisk.change_reason,
              },
            };
          });

          // Fetch stance in background if score changed
          fetch(`${API}/api/stocks/${encodeURIComponent(ticker)}/decision`, { cache: "no-store" })
            .then((r) => r.ok && r.json())
            .then((decisionData) => {
              if (decisionData) {
                setDetail((prev) => (prev ? { ...prev, decision: decisionData } : prev));
              }
            })
            .catch(() => {});
        } else {
          // Preserve last valid score on failure
          setDetail((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              risk: {
                ...prev.risk,
                data_freshness: "stale",
                change_reason: `Sync unavailable (HTTP ${res.status}) — preserved last verified score`,
              },
            };
          });
        }
      } catch (err) {
        // Network or timeout failure: preserve score, annotate stale
        setDetail((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            risk: {
              ...prev.risk,
              data_freshness: "stale",
              change_reason: "Connection paused — displaying cached baseline score",
            },
          };
        });
      } finally {
        inFlightRef.current = false;
        setSyncing(false);
        setCountdown(15);
      }
    },
    [ticker]
  );

  // Fetch Risk Audit History
  const loadHistory = useCallback(async () => {
    if (!ticker) return;
    setHistoryLoading(true);
    try {
      const res = await fetch(`${API}/api/stocks/${encodeURIComponent(ticker)}/risk/history?limit=15`, {
        cache: "no-store",
      });
      if (res.ok) {
        const json = await res.json();
        setHistoryList(json.history || []);
      }
    } catch {
      // ignore
    } finally {
      setHistoryLoading(false);
    }
  }, [ticker]);

  // Live Auto-Refresh Polling Loop (15 seconds, pauses when tab is hidden)
  useEffect(() => {
    if (!ticker || !autoSync) return;

    const timer = setInterval(() => {
      if (document.hidden) return; // tab hidden -> pause timer
      setCountdown((prev) => {
        if (prev <= 1) {
          syncRiskScore(false);
          return 15;
        }
        return prev - 1;
      });
    }, 1000);

    const handleVisibility = () => {
      if (!document.hidden && autoSync) {
        syncRiskScore(false);
        setCountdown(15);
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [ticker, autoSync, syncRiskScore]);

  function bandClass(band?: string) {
    if (band === "High") return "border-rose-500/40 bg-rose-500/15 text-rose-300";
    if (band === "Elevated") return "border-amber-500/40 bg-amber-500/15 text-amber-300";
    if (band === "Low") return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
    return "border-white/10 bg-white/[0.04] text-slate-400";
  }

  function freshnessBadge(status?: string) {
    if (status === "live") {
      return (
        <span className="flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-300">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          LIVE (Exchange Ticks)
        </span>
      );
    }
    if (status === "stale") {
      return (
        <span className="flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-amber-300">
          <AlertTriangle className="h-3 w-3 text-amber-400" />
          STALE (Cached Observations)
        </span>
      );
    }
    return (
      <span className="flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-sky-300">
        <CheckCircle2 className="h-3 w-3 text-sky-400" />
        VERIFIED (Session Cache)
      </span>
    );
  }

  return (
    <main className="min-h-screen bg-[#05070a] text-slate-100 flex flex-col bg-terminal-grid">
      <Navbar />

      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 sm:py-12 flex-1">
        {/* Breadcrumb Navigation & Top Telemetry */}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500 font-mono">
          <div className="flex items-center gap-2">
            <Link href="/stocks" className="flex items-center gap-1 hover:text-cyan-400 transition">
              <ArrowLeft className="h-3.5 w-3.5" /> Equities Screener
            </Link>
            <ChevronRight className="h-3 w-3 text-zinc-600" />
            <span className="text-white font-bold tracking-wider">{ticker}</span>
            <span className="rounded bg-sky-500/10 border border-sky-500/30 px-1.5 py-0.5 text-[10px] text-sky-400 font-semibold">
              QUANT TERMINAL
            </span>
          </div>

          {/* Live Sync Status Pill */}
          <div className="flex items-center gap-3">
            {freshnessBadge(detail?.risk?.data_freshness)}
            <div className="flex items-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-950/80 px-2.5 py-1 text-[11px] text-zinc-400 font-mono">
              <Activity className="h-3 w-3 text-sky-400" />
              <span>Sync in {countdown}s</span>
            </div>
            <button
              onClick={() => syncRiskScore(true)}
              disabled={syncing}
              className="flex items-center gap-1 rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-zinc-800 hover:border-sky-500/50 transition disabled:opacity-50"
              title="Force recalculate risk engine now"
            >
              <RefreshCw className={`h-3 w-3 text-sky-400 ${syncing ? "animate-spin" : ""}`} />
              <span>{syncing ? "Recalculating..." : "Sync Now"}</span>
            </button>
            <button
              onClick={() => {
                setShowHistory((prev) => !prev);
                if (!showHistory) loadHistory();
              }}
              className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900/60 px-2.5 py-1 text-[11px] font-medium text-zinc-300 hover:bg-zinc-800 hover:text-white transition"
            >
              <History className="h-3 w-3 text-zinc-400" />
              <span>{showHistory ? "Hide Timeline" : "Risk Timeline"}</span>
            </button>
          </div>
        </div>

        {/* Dynamic Change Notification Banner */}
        {syncNotice && (
          <div className="mb-6 rounded-xl border border-sky-500/30 bg-sky-500/10 p-3 text-xs text-sky-200 flex items-center gap-2 animate-fadeIn">
            <Activity className="h-4 w-4 text-sky-400 animate-pulse flex-shrink-0" />
            <span>{syncNotice}</span>
          </div>
        )}

        {loading && (
          <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-12 text-center">
            <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-sky-400 border-t-transparent mb-3" />
            <p className="text-sm text-zinc-400">Loading {ticker} live risk indicators and market telemetry...</p>
          </div>
        )}

        {error && (
          <div className="rounded-2xl border border-red-900 bg-red-950/30 p-8">
            <h2 className="text-lg font-semibold text-red-300">Could not load stock</h2>
            <p className="mt-1 text-sm text-red-400/80">{error}</p>
            <Link
              href="/stocks"
              className="mt-4 inline-block rounded-lg bg-zinc-800 px-4 py-2 text-xs font-semibold text-white hover:bg-zinc-700"
            >
              Back to Stocks
            </Link>
          </div>
        )}

        {!loading && !error && (
          <div className="space-y-8">
            {/* Header info */}
            <div className="flex flex-wrap items-start justify-between gap-6 border-b border-zinc-900 pb-8">
              <div>
                <div className="flex flex-wrap items-center gap-3">
                  <h1 className="text-4xl font-extrabold tracking-tight text-white font-mono">{ticker}</h1>
                  <span
                    className={`inline-flex rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wider ${bandClass(
                      detail?.risk?.band
                    )}`}
                  >
                    Risk Band: {detail?.risk?.band || "Unknown"}
                  </span>
                  {detail?.risk?.score_change != null && detail.risk.score_change !== 0 && (
                    <span
                      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold font-mono ${
                        detail.risk.score_change > 0
                          ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
                          : "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                      }`}
                    >
                      {detail.risk.score_change > 0 ? (
                        <ArrowUpRight className="h-3 w-3" />
                      ) : (
                        <ArrowDownRight className="h-3 w-3" />
                      )}
                      {detail.risk.score_change > 0 ? `+${detail.risk.score_change}` : detail.risk.score_change} pts
                    </span>
                  )}
                </div>
                <p className="mt-2 text-lg text-zinc-300 font-medium">
                  {detail?.meta?.name || "Configured Universe Stock"}
                </p>

                <div className="mt-3 flex flex-wrap gap-4 text-xs text-zinc-400 font-mono">
                  <span className="flex items-center gap-1.5 rounded-lg border border-white/5 bg-zinc-900/60 px-2.5 py-1">
                    <Building2 className="h-3 w-3 text-sky-400" /> Exchange: <strong className="text-white">{detail?.meta?.exchange || "NSE"}</strong>
                  </span>
                  <span className="flex items-center gap-1.5 rounded-lg border border-white/5 bg-zinc-900/60 px-2.5 py-1">
                    <Layers className="h-3 w-3 text-sky-400" /> Segment: <strong className="text-white">{detail?.meta?.segment || "Main"}</strong>
                  </span>
                  <span className="flex items-center gap-1.5 rounded-lg border border-white/5 bg-zinc-900/60 px-2.5 py-1">
                    <Clock className="h-3 w-3 text-sky-400" /> Calculated: <strong className="text-zinc-200">{formatIsoTime(detail?.risk?.calculated_at)}</strong>
                  </span>
                  {detail?.risk?.market_data_as_of && (
                    <span className="flex items-center gap-1.5 rounded-lg border border-white/5 bg-zinc-900/60 px-2.5 py-1">
                      <Activity className="h-3 w-3 text-emerald-400" /> Market Data: <strong className="text-zinc-200">{formatIsoTime(detail?.risk?.market_data_as_of)}</strong>
                    </span>
                  )}
                </div>
              </div>

              {/* Dynamic Score Box with Flash Transition */}
              <div
                onClick={() => {
                  const el = document.getElementById("risk-breakdown-section");
                  if (el) el.scrollIntoView({ behavior: "smooth" });
                }}
                className={`cursor-pointer rounded-2xl border p-5 text-right min-w-[210px] transition-all group shadow-sm ${
                  scoreFlash === "up"
                    ? "border-rose-500 bg-rose-950/40 ring-2 ring-rose-500/50 scale-105"
                    : scoreFlash === "down"
                    ? "border-emerald-500 bg-emerald-950/40 ring-2 ring-emerald-500/50 scale-105"
                    : "border-zinc-800 bg-zinc-950/80 hover:border-sky-500/50 hover:bg-zinc-900"
                }`}
                title="Click to unpack contribution breakdown with weights"
              >
                <div className="flex items-center justify-end gap-1.5 text-xs uppercase tracking-wider text-zinc-500 group-hover:text-sky-300 transition-colors font-semibold">
                  <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-ping" />
                  Live Dakota Score
                </div>
                <div className="mt-1 font-mono text-4xl font-extrabold text-white group-hover:scale-105 transition-transform tabular-nums">
                  {detail?.risk?.score != null ? detail.risk.score : "—"}
                  <span className="text-sm font-normal text-zinc-600">/100</span>
                </div>
                {detail?.risk?.change_reason && (
                  <div className="mt-1 text-[11px] text-zinc-400 max-w-[200px] truncate" title={detail.risk.change_reason}>
                    {detail.risk.change_reason}
                  </div>
                )}
                <div className="mt-1.5 text-[11px] font-semibold text-sky-400 group-hover:underline">
                  Click to unpack breakdown →
                </div>
              </div>
            </div>

            {/* Risk History Timeline Drawer (Expandable) */}
            {showHistory && (
              <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-6 animate-fadeIn">
                <div className="flex items-center justify-between pb-4 border-b border-zinc-900">
                  <div className="flex items-center gap-2">
                    <History className="h-4 w-4 text-sky-400" />
                    <h3 className="text-sm font-semibold text-white uppercase tracking-wider font-mono">
                      Risk Assessment Audit Timeline & Explainability Log
                    </h3>
                  </div>
                  <span className="text-xs text-zinc-500 font-mono">
                    {historyList.length} recorded events
                  </span>
                </div>

                {historyLoading ? (
                  <div className="py-8 text-center text-xs text-zinc-400">Loading audit history...</div>
                ) : historyList.length === 0 ? (
                  <div className="py-8 text-center text-xs text-zinc-500">
                    No score shifts recorded yet. As live ticks change market indicators, recalculations are preserved here.
                  </div>
                ) : (
                  <div className="mt-4 divide-y divide-zinc-900">
                    {historyList.map((item, idx) => (
                      <div key={item.id || idx} className="py-3 flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
                        <div className="flex items-center gap-3">
                          <span className={`px-2 py-0.5 rounded font-bold ${bandClass(item.band)}`}>
                            {item.score} / 100
                          </span>
                          <span className="text-zinc-400">{formatIsoTime(item.calculated_at)}</span>
                          <span className="text-zinc-300 font-sans">{item.change_reason || "Dynamic market evaluation"}</span>
                        </div>
                        {item.score_change != null && item.score_change !== 0 && (
                          <span className={`font-semibold ${item.score_change > 0 ? "text-rose-400" : "text-emerald-400"}`}>
                            {item.score_change > 0 ? `+${item.score_change}` : item.score_change} pts
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Unified 3-Pillar Investment Stance & Decision Card */}
            <section>
              <InvestmentStanceCard ticker={ticker} initialData={detail?.decision} />
            </section>

            {/* Interactive Price & Anomaly Chart */}
            <section>
              <h2 className="mb-4 text-xl font-semibold text-white">Real Market Price Tracker</h2>
              <StockChart
                ticker={ticker}
                stockName={detail?.meta?.name}
                riskInfo={{
                  score: detail?.risk?.score ?? null,
                  band: detail?.risk?.band || "Unknown",
                  verdict: detail?.risk?.verdict,
                }}
                showDetailsLink={false}
              />
            </section>

            {/* Technical Indicator Consensus Gauge */}
            <section>
              <TechnicalSignals
                ticker={ticker}
                tipMarkers={detail?.risk?.band === "High" ? 3 : 0}
              />
            </section>

            {/* Detailed Risk Contribution Breakdown */}
            <section id="risk-breakdown-section">
              <RiskRing
                score={detail?.risk?.score ?? 0}
                contributions={detail?.risk?.contributions}
                contribution_labels={detail?.risk?.contribution_labels}
                weights={detail?.risk?.weights}
                reasons={detail?.risk?.reasons}
                ticker={ticker}
                defaultExpanded={true}
              />
            </section>

            {/* Quick Navigation & Forensic Jumps */}
            <div className="flex flex-wrap items-center gap-3 pt-4 border-t border-zinc-900">
              <Link
                href="/stocks"
                className="flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/80 px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-zinc-800 hover:border-zinc-700"
              >
                <ArrowLeft className="h-3.5 w-3.5" /> All Stocks Screener
              </Link>
              <Link
                href={`/portfolio`}
                className="flex items-center gap-2 rounded-xl border border-white/10 bg-zinc-900/50 px-4 py-2.5 text-xs font-semibold text-zinc-300 transition hover:bg-zinc-800 hover:text-white"
              >
                <Briefcase className="h-3.5 w-3.5 text-amber-400" /> Track in Portfolio
              </Link>
              <Link
                href={`/investigate`}
                className="flex items-center gap-2 rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-4 py-2.5 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-500/20"
              >
                <Radio className="h-3.5 w-3.5" /> Forensic Wire Surveillance
              </Link>
              <Link
                href="/"
                className="flex items-center gap-2 rounded-xl bg-sky-500 px-4 py-2.5 text-xs font-semibold text-slate-950 transition hover:bg-sky-400 ml-auto"
              >
                <ShieldAlert className="h-3.5 w-3.5" /> Analyze Telegram/SMS Tips
              </Link>
            </div>
          </div>
        )}

        <footer className="mt-16 border-t border-zinc-900 pt-6 text-sm text-zinc-600">
          Dakota • Dynamic Risk Engine & Continuous Market Telemetry
        </footer>
      </div>
    </main>
  );
}

export default function StockDetailPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[#05070a] text-slate-100 flex flex-col bg-terminal-grid">
          <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 sm:py-12 flex-1">
            <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-12 text-center">
              <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-sky-400 border-t-transparent mb-3" />
              <p className="text-sm text-zinc-400">Loading scrip telemetry and risk indicators...</p>
            </div>
          </div>
        </main>
      }
    >
      <StockDetailContent />
    </Suspense>
  );
}
