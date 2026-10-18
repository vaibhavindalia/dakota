"use client";

import Link from "next/link";
import React, { useEffect, useState } from "react";
import Navbar from "@/components/Navbar";
import { TopRiskChart } from "@/components/RiskCharts";
import StockChart from "@/components/StockChart";
import { 
  Search, 
  RefreshCw, 
  TrendingUp, 
  ChevronRight, 
  ExternalLink, 
  X 
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Stock = {
  ticker: string;
  name: string;
  exchange: string;
  segment: string;
  role: string;
  score: number | null;
  band: string;
  verdict: string;
  latest_price?: number | null;
  change_pct?: number | null;
  volume?: number | null;
  is_surveillance?: number | boolean;
  status?: string;
  updated_at?: string | null;
};

export default function StocksPage() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);

  // Search & Filter States
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedSegment, setSelectedSegment] = useState("");
  const [selectedBand, setSelectedBand] = useState("");
  const [page, setPage] = useState(1);
  const [totalStocks, setTotalStocks] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [globalTotal, setGlobalTotal] = useState(2615);
  const [globalAssessed, setGlobalAssessed] = useState(497);
  const [syncing, setSyncing] = useState(false);

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm);
      setPage(1);
    }, 250);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  useEffect(() => {
    let cancelled = false;

    async function loadStocks() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams();
        if (debouncedSearch) params.set("search", debouncedSearch);
        if (selectedSegment) params.set("segment", selectedSegment);
        if (selectedBand) params.set("band", selectedBand);
        params.set("page", page.toString());
        params.set("limit", "50");

        const response = await fetch(`${API}/api/stocks?${params.toString()}`, {
          cache: "no-store",
        });

        const data: any = await response.json();

        if (!response.ok) {
          throw new Error(data.detail ? data.detail : "Could not load stocks.");
        }

        if (!cancelled) {
          const stocksArray = Array.isArray(data) ? data : data.stocks ?? [];
          setStocks(stocksArray);
          setTotalStocks(data.total ?? stocksArray.length);
          setTotalPages(data.total_pages ?? Math.max(1, Math.ceil((data.total ?? stocksArray.length) / 50)));
          if (data.global_total) setGlobalTotal(data.global_total);
          if (data.global_assessed) setGlobalAssessed(data.global_assessed);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load stocks.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadStocks();
    return () => {
      cancelled = true;
    };
  }, [debouncedSearch, selectedSegment, selectedBand, page]);

  async function triggerSyncBatch() {
    if (syncing) return;
    setSyncing(true);
    try {
      const res = await fetch(`${API}/api/stocks/sync-batch?limit=15`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setGlobalAssessed(data.global_assessed);
        // refresh current page data
        setPage((p) => p);
      }
    } catch {
      // ignore
    } finally {
      setSyncing(false);
    }
  }

  function bandClass(band: string) {
    if (band === "High") {
      return "border-red-900/60 bg-red-950/30 text-red-300";
    }
    if (band === "Elevated") {
      return "border-orange-900/60 bg-orange-950/30 text-orange-300";
    }
    if (band === "Low") {
      return "border-emerald-900/60 bg-emerald-950/30 text-emerald-300";
    }
    return "border-zinc-800 bg-zinc-900/60 text-zinc-400";
  }

  function toggleStock(stock: Stock) {
    if (selectedStock?.ticker === stock.ticker) {
      setSelectedStock(null);
    } else {
      setSelectedStock(stock);
    }
  }

  return (
    <main className="min-h-screen bg-[#05070a] text-slate-100 flex flex-col bg-terminal-grid">
      <Navbar />

      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 sm:py-12 flex-1">
        <header className="mb-8">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/[0.08] pb-6">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-mono font-semibold text-cyan-300 mb-3">
                <TrendingUp className="h-3.5 w-3.5" />
                <span>ALL INDIA EQUITIES UNIVERSE</span>
              </div>
              <h1 className="text-3xl sm:text-4xl font-black text-white">
                Indian Equities Screener
              </h1>
              <p className="mt-2 max-w-2xl text-sm text-slate-400">
                Directory of <span className="font-semibold text-white">{globalTotal.toLocaleString()} Indian securities</span> across NSE and BSE. Real-time forensic risk scoring, 200 SMA, Bollinger Bands, and Supertrend overlays.
              </p>
            </div>

            {/* Live Database & Sync Status Badge */}
            <div className="flex items-center gap-4 rounded-xl border border-white/[0.08] bg-white/[0.02] p-3 shadow-lg backdrop-blur-md">
              <div className="flex items-center gap-2.5">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                </span>
                <div>
                  <div className="text-xs font-mono font-bold text-white">
                    {globalAssessed.toLocaleString()} / {globalTotal.toLocaleString()} Pre-Computed
                  </div>
                  <div className="text-[10px] text-slate-500">
                    SQLite Local Cache • Instant Search
                  </div>
                </div>
              </div>

              <button
                onClick={triggerSyncBatch}
                disabled={syncing}
                title="Trigger background forensic assessment for next batch"
                className="flex items-center gap-1.5 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-mono font-semibold text-cyan-300 hover:bg-cyan-500/20 disabled:opacity-50 transition"
              >
                <RefreshCw className={`w-3 h-3 ${syncing ? "animate-spin" : ""}`} />
                <span>{syncing ? "Syncing..." : "Sync Batch"}</span>
              </button>
            </div>
          </div>
        </header>

        {/* Live Top Risk Visualizer */}
        {!loading && !error && stocks.length > 0 && (
          <div className="mb-6">
            <TopRiskChart stocks={stocks} />
          </div>
        )}

        {/* Search and Filters Toolbar */}
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute inset-y-0 left-3 my-auto w-4 h-4 text-slate-500" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search 2,600+ equities (e.g. RELIANCE, ZOMATO, BASILIC)..."
              className="w-full rounded-xl border border-white/[0.08] bg-[#0a0e17] pl-10 pr-9 py-2 text-xs text-white placeholder-slate-500 outline-none transition focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/30 font-medium"
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm("")}
                className="absolute inset-y-0 right-3 my-auto text-slate-500 hover:text-white"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Segment & Risk Category Pills */}
          <div className="flex flex-wrap items-center gap-1.5">
            {[
              { label: "All Stocks", seg: "", band: "" },
              { label: "High Risk", seg: "", band: "High" },
              { label: "Elevated", seg: "", band: "Elevated" },
              { label: "Low Risk", seg: "", band: "Low" },
              { label: "Main Board", seg: "main", band: "" },
              { label: "Surveillance", seg: "surveillance", band: "" },
              { label: "SME", seg: "sme", band: "" },
            ].map((f) => {
              const isActive = selectedSegment === f.seg && selectedBand === f.band;
              return (
                <button
                  key={f.label}
                  onClick={() => {
                    setSelectedSegment(f.seg);
                    setSelectedBand(f.band);
                    setPage(1);
                  }}
                  className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                    isActive
                      ? "bg-cyan-500/20 text-cyan-300 border border-cyan-400/40 shadow-sm shadow-cyan-500/10"
                      : "bg-white/[0.03] text-slate-400 border border-white/5 hover:text-white hover:bg-white/[0.06]"
                  }`}
                >
                  {f.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Loading state */}
        {loading && (
          <div className="mt-8 rounded-2xl border border-white/[0.08] bg-[#0a0e17] p-12 text-center">
            <div className="inline-flex items-center gap-3 text-sm text-cyan-400 font-mono">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
              <span>Scanning equities universe...</span>
            </div>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="mt-8 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-6 text-sm text-rose-300">
            {error}
          </div>
        )}

        {/* Stock table */}
        {!loading && !error && (
          <section className="mt-8 overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0a0e17] shadow-2xl">
            <div className="border-b border-white/[0.08] px-6 py-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="text-base font-bold text-white">Indian Securities Screener</h2>
                  <p className="mt-0.5 text-xs text-slate-500">
                    Showing {stocks.length} of {totalStocks.toLocaleString()} stocks • Click any row to expand interactive price chart
                  </p>
                </div>

                {selectedStock && (
                  <button
                    onClick={() => setSelectedStock(null)}
                    className="rounded-lg border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300 hover:text-white"
                  >
                    Close Active Chart ({selectedStock.ticker}) ✕
                  </button>
                )}
              </div>
            </div>

            {/* Desktop table */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-white/[0.08] bg-white/[0.01] text-[11px] font-mono uppercase tracking-wider text-slate-400">
                    <th className="px-6 py-3.5">Security / Company</th>
                    <th className="px-6 py-3.5">Exchange</th>
                    <th className="px-6 py-3.5">Segment</th>
                    <th className="px-6 py-3.5 text-right">Risk Score</th>
                    <th className="px-6 py-3.5">Assessment Tier</th>
                    <th className="px-6 py-3.5 text-center">Interactive Graph</th>
                  </tr>
                </thead>

                <tbody>
                  {stocks.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-12 text-center text-zinc-500">
                        No stocks found matching &ldquo;{debouncedSearch}&rdquo;. Try another symbol or filter.
                      </td>
                    </tr>
                  ) : (
                    stocks.map((stock) => {
                      const isSelected = selectedStock?.ticker === stock.ticker;
                      return (
                        <React.Fragment key={stock.ticker}>
                          <tr
                            onClick={() => toggleStock(stock)}
                            className={`cursor-pointer border-b transition ${
                              isSelected
                                ? "border-sky-500/40 bg-sky-500/[0.08]"
                                : "border-zinc-900 hover:bg-zinc-900/60"
                            }`}
                          >
                            <td className="px-6 py-4">
                              <div className="font-semibold text-white group-hover:text-sky-300">
                                {stock.ticker}
                              </div>
                              <div className="mt-0.5 text-xs text-zinc-500 max-w-xs truncate">
                                {stock.name}
                              </div>
                            </td>

                            <td className="px-6 py-4 text-sm text-zinc-400">
                              {stock.exchange}
                            </td>

                            <td className="px-6 py-4 text-sm text-zinc-400">
                              <span className={stock.is_surveillance ? "text-amber-400 font-medium" : ""}>
                                {stock.is_surveillance ? "Surveillance (BE/BZ)" : stock.segment}
                              </span>
                            </td>

                            <td className="px-6 py-4 text-right">
                              <span className="text-lg font-semibold">
                                {stock.score != null ? stock.score : "—"}
                              </span>
                              {stock.score != null && (
                                <span className="text-xs text-zinc-600"> /100</span>
                              )}
                            </td>

                            <td className="px-6 py-4">
                              <span
                                className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${bandClass(
                                  stock.band
                                )}`}
                              >
                                {stock.band || "Pending"}
                              </span>
                            </td>

                            <td className="px-6 py-4 text-center">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleStock(stock);
                                }}
                                className={`rounded-lg border px-3 py-1 text-xs font-semibold transition ${
                                  isSelected
                                    ? "border-sky-400 bg-sky-500/20 text-sky-300"
                                    : "border-white/10 bg-white/[0.03] text-white/60 hover:border-sky-400/40 hover:text-white"
                                }`}
                              >
                                {isSelected ? "Hide ▲" : "Graph ▼"}
                              </button>
                            </td>
                          </tr>

                          {/* Expandable Chart Row */}
                          {isSelected && (
                            <tr className="border-b border-sky-500/30 bg-[#070b14]">
                              <td colSpan={6} className="p-5">
                                <StockChart
                                  ticker={stock.ticker}
                                  stockName={stock.name}
                                  riskInfo={{
                                    score: stock.score,
                                    band: stock.band,
                                    verdict: stock.verdict,
                                  }}
                                  onClose={() => setSelectedStock(null)}
                                  showDetailsLink={true}
                                />
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="divide-y divide-zinc-900 md:hidden">
              {stocks.map((stock) => {
                const isSelected = selectedStock?.ticker === stock.ticker;
                return (
                  <div key={stock.ticker} className="p-5">
                    <div
                      onClick={() => toggleStock(stock)}
                      className="cursor-pointer"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="text-lg font-semibold text-white">
                            {stock.ticker}
                          </div>
                          <div className="mt-0.5 text-xs text-zinc-500 line-clamp-1">
                            {stock.name}
                          </div>
                          <div className="mt-2 text-xs text-zinc-600">
                            {stock.exchange} • {stock.is_surveillance ? "Surveillance" : stock.segment}
                          </div>
                        </div>

                        <div className="text-right">
                          <div className="text-xl font-bold">
                            {stock.score != null ? stock.score : "—"}
                          </div>
                          <span
                            className={`mt-2 inline-flex rounded-full border px-3 py-1 text-xs font-medium ${bandClass(
                              stock.band
                            )}`}
                          >
                            {stock.band || "Pending"}
                          </span>
                        </div>
                      </div>

                      <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-3">
                        <span className="text-xs text-sky-400 font-medium">
                          {isSelected ? "Hide price chart ▲" : "Tap to view price chart ▼"}
                        </span>
                        <Link
                          href={`/stocks/${stock.ticker}`}
                          onClick={(e) => e.stopPropagation()}
                          className="text-xs text-white/50 hover:text-white"
                        >
                          Deep-dive →
                        </Link>
                      </div>
                    </div>

                    {/* Mobile Expandable Chart */}
                    {isSelected && (
                      <div className="mt-4 pt-3 border-t border-sky-500/20">
                        <StockChart
                          ticker={stock.ticker}
                          stockName={stock.name}
                          riskInfo={{
                            score: stock.score,
                            band: stock.band,
                            verdict: stock.verdict,
                          }}
                          onClose={() => setSelectedStock(null)}
                          showDetailsLink={true}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex flex-wrap items-center justify-between gap-4 border-t border-zinc-800 px-6 py-4">
                <div className="text-xs text-zinc-400">
                  Showing <span className="font-semibold text-white">{(page - 1) * 50 + 1}</span>–
                  <span className="font-semibold text-white">{Math.min(page * 50, totalStocks)}</span> of{" "}
                  <span className="font-semibold text-white">{totalStocks.toLocaleString()}</span> matching Indian stocks
                </div>

                <div className="flex items-center gap-2">
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-white/10 disabled:opacity-40 disabled:hover:bg-white/[0.04]"
                  >
                    ← Previous
                  </button>

                  <span className="text-xs text-zinc-400 px-2">
                    Page <span className="text-white font-semibold">{page}</span> of{" "}
                    <span className="text-white font-semibold">{totalPages}</span>
                  </span>

                  <button
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-white/10 disabled:opacity-40 disabled:hover:bg-white/[0.04]"
                  >
                    Next →
                  </button>
                </div>
              </div>
            )}
          </section>
        )}

        <div className="mt-8">
          <Link
            href="/"
            className="inline-block rounded-xl bg-white px-5 py-3 font-semibold text-black transition hover:bg-zinc-200"
          >
            Back to Tip Check
          </Link>
        </div>

        <footer className="mt-16 border-t border-zinc-900 pt-6 text-sm text-zinc-600">
          Dakota • Full Indian Market Intelligence • 2,600+ NSE & BSE Equities
        </footer>
      </div>
    </main>
  );
}