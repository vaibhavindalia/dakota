"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import { 
  Briefcase, 
  Plus, 
  Trash2, 
  ExternalLink, 
  ShieldAlert, 
  CheckCircle2, 
  AlertTriangle,
  Layers,
  ArrowRight,
  RefreshCw,
  Edit3,
  TrendingUp,
  TrendingDown,
  HelpCircle,
  Info,
  ShieldCheck,
  DollarSign,
  PieChart,
  SlidersHorizontal,
  X
} from "lucide-react";

type Risk = {
  score?: number | null;
  band?: string;
  verdict?: string;
  as_of?: string;
  reasons?: string[];
};

type Holding = {
  ticker: string;
  name: string;
  exchange: string;
  bse_code?: string | null;
  quantity: number;
  average_buy_price: number | null;
  current_price: number | null;
  current_value: number | null;
  market_value: number | null;
  actual_cost_basis: number | null;
  estimated_cost_basis: number | null;
  has_actual_cost: boolean;
  cost_basis_type: "actual" | "estimated" | "unavailable";
  valuation_status: string;
  unrealized_pnl: number | null;
  unrealized_return_pct: number | null;
  quote_status: string;
  quote_timestamp?: string | null;
  change?: number;
  change_pct?: number;
  currency?: string;
  risk?: Risk | null;
};

type PortfolioSummary = {
  total_positions: number;
  total_actual_cost: number;
  total_estimated_cost: number;
  total_market_value: number;
  total_unrealized_pnl: number | null;
  total_unrealized_return_pct: number | null;
  unpriced_count: number;
  missing_buy_price_count: number;
  verified_buy_price_count: number;
  is_partial_valuation: boolean;
  as_of?: string;
  currency?: string;
  total_invested?: number;
  count?: number;
};

type PortfolioResponse = PortfolioSummary & {
  holdings: Holding[];
  summary?: PortfolioSummary;
};

type ActiveTab = "holdings" | "manage" | "radar";

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("holdings");
  
  // Form state
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");
  const [averagePrice, setAveragePrice] = useState("");
  const [editingTicker, setEditingTicker] = useState<string | null>(null);

  // Status state
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  async function loadPortfolio(forceRefresh = false) {
    if (forceRefresh) setRefreshing(true);
    try {
      setError("");
      const url = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/portfolio${
        forceRefresh ? "?refresh=true" : ""
      }`;

      const response = await fetch(url, { cache: "no-store" });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail || "Could not load portfolio.");
      }

      setPortfolio(data);
    } catch (err: any) {
      setError(err?.message || String(err) || "Could not load portfolio.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    loadPortfolio();
  }, []);

  async function addOrUpdateHolding(event: FormEvent) {
    event.preventDefault();

    if (!ticker.trim()) {
      setError("Please enter a valid stock ticker symbol (e.g. WIPRO, ZOMATO).");
      return;
    }

    const numQty = Number(quantity);
    if (!quantity || isNaN(numQty) || numQty <= 0) {
      setError("Please enter a valid positive quantity of shares.");
      return;
    }

    let numPrice: number | null = null;
    if (averagePrice.trim() !== "") {
      const parsedPrice = Number(averagePrice);
      if (isNaN(parsedPrice) || parsedPrice < 0) {
        setError("Average buy price must be a non-negative number.");
        return;
      }
      if (parsedPrice > 0) {
        numPrice = parsedPrice;
      }
    }

    setSaving(true);
    setError("");
    setSuccessMsg("");

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/portfolio/holdings`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            ticker: ticker.trim().toUpperCase(),
            exchange: "NSE",
            quantity: numQty,
            average_buy_price: numPrice,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail || "Could not save portfolio holding.");
      }

      const cleanTicker = ticker.trim().toUpperCase();
      setSuccessMsg(
        editingTicker
          ? `Successfully updated position ${cleanTicker}.`
          : `Successfully registered ${numQty} shares of ${cleanTicker}.`
      );

      // Reset form
      setTicker("");
      setQuantity("");
      setAveragePrice("");
      setEditingTicker(null);

      // Reload portfolio data
      await loadPortfolio();
    } catch (err: any) {
      setError(err?.message || String(err) || "Could not save holding.");
    } finally {
      setSaving(false);
    }
  }

  async function removeHolding(stockTicker: string) {
    try {
      setError("");
      setSuccessMsg("");

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/portfolio/holdings/${encodeURIComponent(
          stockTicker
        )}`,
        {
          method: "DELETE",
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail || "Could not remove holding.");
      }

      setSuccessMsg(`Position ${stockTicker} removed from portfolio.`);
      if (editingTicker === stockTicker) {
        cancelEdit();
      }
      await loadPortfolio();
    } catch (err: any) {
      setError(err?.message || String(err) || "Could not remove holding.");
    }
  }

  function startEdit(holding: Holding) {
    setTicker(holding.ticker);
    setQuantity(String(holding.quantity));
    setAveragePrice(holding.average_buy_price != null ? String(holding.average_buy_price) : "");
    setEditingTicker(holding.ticker);
    setActiveTab("manage");
    window.scrollTo({ top: 320, behavior: "smooth" });
  }

  function cancelEdit() {
    setTicker("");
    setQuantity("");
    setAveragePrice("");
    setEditingTicker(null);
  }

  function selectQuickTicker(sym: string, defaultQty?: string) {
    setTicker(sym);
    if (!quantity && defaultQty) {
      setQuantity(defaultQty);
    }
  }

  function riskClass(band?: string) {
    if (band === "High") return "border-rose-500/40 bg-rose-500/15 text-rose-300";
    if (band === "Elevated") return "border-amber-500/40 bg-amber-500/15 text-amber-300";
    if (band === "Low") return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
    return "border-white/10 bg-white/[0.04] text-slate-400";
  }

  // Summary figures from backend
  const totalPositions = portfolio?.total_positions ?? portfolio?.holdings?.length ?? 0;
  const totalMarketVal = portfolio?.total_market_value ?? 0;
  const totalActualCost = portfolio?.total_actual_cost ?? 0;
  const totalEstCost = portfolio?.total_estimated_cost ?? 0;
  const totalUnrealizedPnl = portfolio?.total_unrealized_pnl ?? null;
  const totalReturnPct = portfolio?.total_unrealized_return_pct ?? null;
  const verifiedCount = portfolio?.verified_buy_price_count ?? 0;
  const missingBuyCount = portfolio?.missing_buy_price_count ?? 0;
  const unpricedCount = portfolio?.unpriced_count ?? 0;

  // Risk breakdown
  const highRiskPositions = portfolio?.holdings.filter((h) => h.risk?.band === "High").length ?? 0;
  const elevatedPositions = portfolio?.holdings.filter((h) => h.risk?.band === "Elevated").length ?? 0;
  const lowRiskPositions = portfolio?.holdings.filter((h) => h.risk?.band === "Low").length ?? 0;

  return (
    <main className="min-h-screen bg-[#05070a] text-slate-100 flex flex-col bg-terminal-grid">
      <Navbar />

      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 sm:py-12 flex-1">
        {/* Header Section */}
        <header className="mb-8">
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 border-b border-white/[0.08] pb-6">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-mono font-semibold text-cyan-300 mb-3">
                <Briefcase className="h-3.5 w-3.5" />
                <span>DAKOTA PORTFOLIO SURVEILLANCE &amp; MULTI-HOLDING ENGINE</span>
              </div>
              <h1 className="text-3xl sm:text-4xl font-black text-white tracking-tight">
                Portfolio Valuation &amp; Risk Station
              </h1>
              <p className="mt-2 max-w-2xl text-sm text-slate-400">
                Audited multi-asset valuation across Indian equities. Accurately distinguishes verified historical cost basis from live estimated market valuation, synchronized with Dakota&apos;s forensic risk radar.
              </p>
            </div>

            {/* Quick Actions */}
            <div className="flex items-center gap-3">
              <button
                onClick={() => loadPortfolio(true)}
                disabled={refreshing || loading}
                className="inline-flex items-center gap-2 rounded-xl border border-white/[0.1] bg-white/[0.03] px-3.5 py-2 text-xs font-mono font-medium text-slate-300 hover:border-cyan-500/40 hover:text-cyan-300 transition disabled:opacity-50"
                title="Refresh market quotes and valuation"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin text-cyan-400" : ""}`} />
                <span>{refreshing ? "Refreshing Quotes..." : "Refresh Quotes"}</span>
              </button>
            </div>
          </div>

          {/* Persistent Summary Stats Bar */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mt-6">
            {/* Total Positions */}
            <div className="rounded-xl border border-white/[0.08] bg-[#0a0e17] p-3.5 shadow-sm">
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Total Holdings</div>
              <div className="text-xl font-bold font-mono text-white mt-1">
                {totalPositions} <span className="text-xs font-normal text-slate-500">Scrips</span>
              </div>
              <div className="text-[10px] text-slate-500 mt-0.5">
                {unpricedCount > 0 ? (
                  <span className="text-amber-400">{unpricedCount} unpriced quote(s)</span>
                ) : (
                  <span>All positions quoted</span>
                )}
              </div>
            </div>

            {/* Current Market Value */}
            <div className="rounded-xl border border-cyan-500/20 bg-cyan-950/20 p-3.5 shadow-sm">
              <div className="text-[10px] font-mono uppercase tracking-wider text-cyan-400 flex items-center justify-between">
                <span>Current Market Value</span>
              </div>
              <div className="text-xl font-bold font-mono text-white mt-1">
                ₹{totalMarketVal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className="text-[10px] text-cyan-300/70 mt-0.5">
                Qty × Live Market Price
              </div>
            </div>

            {/* Actual Cost Basis */}
            <div className="rounded-xl border border-white/[0.08] bg-[#0a0e17] p-3.5 shadow-sm">
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 flex items-center justify-between">
                <span>Actual Cost Basis</span>
                <span className="rounded bg-emerald-500/10 px-1 py-0.2 text-[9px] font-mono text-emerald-400">
                  {verifiedCount} Verified
                </span>
              </div>
              <div className="text-xl font-bold font-mono text-emerald-400 mt-1">
                ₹{totalActualCost.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className="text-[10px] text-slate-500 mt-0.5">
                Qty × Verified Buy Price
              </div>
            </div>

            {/* Estimated Cost Basis */}
            <div className="rounded-xl border border-white/[0.08] bg-[#0a0e17] p-3.5 shadow-sm">
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 flex items-center justify-between">
                <span>Est. Cost Basis</span>
                {missingBuyCount > 0 && (
                  <span className="rounded bg-amber-500/10 px-1 py-0.2 text-[9px] font-mono text-amber-400">
                    {missingBuyCount} Unrecorded
                  </span>
                )}
              </div>
              <div className="text-xl font-bold font-mono text-amber-300 mt-1">
                ₹{totalEstCost.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className="text-[10px] text-slate-500 mt-0.5">
                Qty × Market Price (Estimate)
              </div>
            </div>

            {/* Unrealized P/L */}
            <div className="rounded-xl border border-white/[0.08] bg-[#0a0e17] p-3.5 shadow-sm">
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                Unrealized P/L
              </div>
              <div className="text-xl font-bold font-mono mt-1">
                {totalUnrealizedPnl != null ? (
                  <span className={totalUnrealizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"}>
                    {totalUnrealizedPnl >= 0 ? "+" : ""}₹{totalUnrealizedPnl.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                ) : (
                  <span className="text-slate-500 text-sm">N/A (No Buy Price)</span>
                )}
              </div>
              <div className="text-[10px] text-slate-500 mt-0.5">
                {totalReturnPct != null ? (
                  <span className={totalReturnPct >= 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                    {totalReturnPct >= 0 ? "+" : ""}{totalReturnPct.toFixed(2)}% Return
                  </span>
                ) : (
                  "Verified Positions Only"
                )}
              </div>
            </div>

            {/* Risk Profile */}
            <div className="rounded-xl border border-white/[0.08] bg-[#0a0e17] p-3.5 shadow-sm">
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                Forensic Risk
              </div>
              <div className="flex items-center gap-2 mt-2">
                <span className="text-xs font-bold text-rose-400 font-mono">{highRiskPositions} High</span>
                <span className="text-xs font-bold text-amber-400 font-mono">{elevatedPositions} Elev</span>
                <span className="text-xs font-bold text-emerald-400 font-mono">{lowRiskPositions} Safe</span>
              </div>
              <div className="text-[10px] text-slate-500 mt-1">
                SEBI &amp; Pump Monitor
              </div>
            </div>
          </div>
        </header>

        {/* Alerts and Feedback */}
        {error && (
          <div className="mb-6 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-300 flex items-start gap-3">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <div>{error}</div>
          </div>
        )}

        {successMsg && (
          <div className="mb-6 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-xs text-emerald-300 flex items-start justify-between gap-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>{successMsg}</span>
            </div>
            <button onClick={() => setSuccessMsg("")} className="text-slate-400 hover:text-white">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* 3-Tab Segmented Navigation */}
        <div className="mb-6 border-b border-white/[0.08]">
          <nav className="flex space-x-2 sm:space-x-4">
            <button
              onClick={() => setActiveTab("holdings")}
              className={`flex items-center gap-2 px-4 py-3 text-xs sm:text-sm font-semibold border-b-2 transition font-mono ${
                activeTab === "holdings"
                  ? "border-cyan-400 text-cyan-300 bg-white/[0.02]"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:border-white/20"
              }`}
            >
              <Briefcase className="w-4 h-4" />
              <span>Tab 1: Holdings &amp; Valuation</span>
              <span className="ml-1 rounded-full bg-white/[0.08] px-2 py-0.5 text-[10px] text-slate-300">
                {totalPositions}
              </span>
            </button>

            <button
              onClick={() => setActiveTab("manage")}
              className={`flex items-center gap-2 px-4 py-3 text-xs sm:text-sm font-semibold border-b-2 transition font-mono ${
                activeTab === "manage"
                  ? "border-cyan-400 text-cyan-300 bg-white/[0.02]"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:border-white/20"
              }`}
            >
              <Plus className="w-4 h-4" />
              <span>Tab 2: Add &amp; Manage Position</span>
              {editingTicker && (
                <span className="rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2 py-0.5 text-[10px]">
                  Editing {editingTicker}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("radar")}
              className={`flex items-center gap-2 px-4 py-3 text-xs sm:text-sm font-semibold border-b-2 transition font-mono ${
                activeTab === "radar"
                  ? "border-cyan-400 text-cyan-300 bg-white/[0.02]"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:border-white/20"
              }`}
            >
              <Layers className="w-4 h-4" />
              <span>Tab 3: Risk &amp; Exposure Radar</span>
              {highRiskPositions > 0 && (
                <span className="rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30 px-2 py-0.5 text-[10px]">
                  {highRiskPositions} High Risk
                </span>
              )}
            </button>
          </nav>
        </div>

        {/* ========================================================================= */}
        {/* TAB 1: HOLDINGS & VALUATION */}
        {/* ========================================================================= */}
        {activeTab === "holdings" && (
          <section className="space-y-6">
            <div className="rounded-2xl border border-white/[0.08] bg-[#0a0e17] shadow-2xl overflow-hidden">
              <div className="border-b border-white/[0.08] px-6 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <span>Registered Portfolio Holdings &amp; Live Valuation</span>
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Position values calculated using real-time quotes, distinguishing actual historical investment from estimated cost basis.
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400 font-mono">
                    {totalPositions} Positions Active
                  </span>
                  <button
                    onClick={() => setActiveTab("manage")}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-500/15 border border-cyan-500/30 px-3 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/25 transition"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Add Stock</span>
                  </button>
                </div>
              </div>

              {loading ? (
                <div className="p-16 text-center text-xs text-cyan-400 font-mono animate-pulse">
                  Retrieving portfolio securities and real-time market data...
                </div>
              ) : totalPositions === 0 ? (
                <div className="p-16 text-center">
                  <Briefcase className="w-10 h-10 text-slate-600 mx-auto mb-3" />
                  <p className="text-base font-semibold text-slate-300">Your portfolio is currently empty</p>
                  <p className="text-xs text-slate-500 mt-1.5 max-w-md mx-auto">
                    Add equities such as Wipro (WIPRO), Zomato (ZOMATO), Reliance, or any Indian stock to monitor live valuation and forensic risk alerts.
                  </p>
                  <button
                    onClick={() => setActiveTab("manage")}
                    className="mt-4 inline-flex items-center gap-2 rounded-xl bg-cyan-500 px-4 py-2 text-xs font-bold text-black hover:bg-cyan-400 transition"
                  >
                    <Plus className="w-4 h-4" />
                    <span>Add First Holding</span>
                  </button>
                </div>
              ) : (
                <div className="divide-y divide-white/[0.04]">
                  {portfolio?.holdings.map((holding) => {
                    const isActual = holding.has_actual_cost;
                    const hasPrice = holding.current_price != null;
                    const pnl = holding.unrealized_pnl;
                    const retPct = holding.unrealized_return_pct;

                    return (
                      <div
                        key={holding.ticker}
                        className="p-6 hover:bg-white/[0.015] transition flex flex-col lg:flex-row lg:items-center justify-between gap-6"
                      >
                        {/* Column 1: Asset Identity & Badges */}
                        <div className="space-y-1.5 lg:w-1/4 shrink-0">
                          <div className="flex items-center gap-2.5">
                            <Link
                              href={`/stocks/${holding.ticker}`}
                              className="text-lg font-black text-white hover:text-cyan-300 transition flex items-center gap-1.5 font-mono"
                              title="Inspect in Stock Terminal"
                            >
                              <span>{holding.ticker}</span>
                              <ExternalLink className="w-3.5 h-3.5 text-slate-500" />
                            </Link>

                            <span className="rounded bg-white/[0.06] border border-white/[0.08] px-2 py-0.5 text-[10px] font-mono text-slate-400">
                              {holding.exchange}
                            </span>

                            {holding.risk?.band && (
                              <span
                                className={`rounded-full border px-2 py-0.5 text-[10px] font-mono font-bold ${riskClass(
                                  holding.risk.band
                                )}`}
                              >
                                {holding.risk.band} RISK
                              </span>
                            )}
                          </div>

                          <div className="text-xs text-slate-300 font-medium">
                            {holding.name}
                          </div>

                          <div className="text-[11px] font-mono text-slate-400 flex items-center gap-2">
                            <span className="text-slate-200 font-semibold">{holding.quantity} shares</span>
                            <span>•</span>
                            {hasPrice ? (
                              <span>
                                Price: ₹{holding.current_price?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                {holding.change_pct != null && (
                                  <span
                                    className={`ml-1 font-semibold ${
                                      holding.change_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                                    }`}
                                  >
                                    ({holding.change_pct >= 0 ? "+" : ""}{holding.change_pct}%)
                                  </span>
                                )}
                              </span>
                            ) : (
                              <span className="text-amber-400">Quote Unavailable</span>
                            )}
                          </div>
                        </div>

                        {/* Column 2: Financial Valuation Metrics */}
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 lg:w-2/4">
                          {/* Cost Basis Block */}
                          <div className="rounded-xl border border-white/[0.05] bg-white/[0.015] p-3">
                            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1">
                              <span>Cost Basis</span>
                              {isActual ? (
                                <span className="rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 px-1 py-0.2 text-[8px] font-bold">
                                  VERIFIED
                                </span>
                              ) : (
                                <span className="rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 px-1 py-0.2 text-[8px] font-bold">
                                  ESTIMATED
                                </span>
                              )}
                            </div>
                            <div className="text-sm sm:text-base font-bold font-mono text-white mt-1">
                              {isActual ? (
                                <span>
                                  ₹{holding.actual_cost_basis?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                </span>
                              ) : holding.estimated_cost_basis != null ? (
                                <span className="text-amber-300">
                                  ₹{holding.estimated_cost_basis?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                </span>
                              ) : (
                                <span className="text-slate-500">Unavailable</span>
                              )}
                            </div>
                            <div className="text-[10px] text-slate-500 mt-0.5 font-mono">
                              {isActual
                                ? `Avg: ₹${holding.average_buy_price?.toLocaleString("en-IN")}`
                                : "Purchase price not recorded"}
                            </div>
                          </div>

                          {/* Current Market Value */}
                          <div className="rounded-xl border border-white/[0.05] bg-white/[0.015] p-3">
                            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                              Market Value
                            </div>
                            <div className="text-sm sm:text-base font-bold font-mono text-cyan-300 mt-1">
                              {holding.current_value != null ? (
                                <span>
                                  ₹{holding.current_value.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                </span>
                              ) : (
                                <span className="text-slate-500">Unavailable</span>
                              )}
                            </div>
                            <div className="text-[10px] text-slate-500 mt-0.5 font-mono">
                              {hasPrice ? `${holding.quantity} × ₹${holding.current_price}` : "Awaiting Quote"}
                            </div>
                          </div>

                          {/* Unrealized P/L */}
                          <div className="col-span-2 sm:col-span-1 rounded-xl border border-white/[0.05] bg-white/[0.015] p-3">
                            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                              Unrealized P/L
                            </div>
                            <div className="text-sm sm:text-base font-bold font-mono mt-1">
                              {isActual && pnl != null ? (
                                <span className={pnl >= 0 ? "text-emerald-400" : "text-rose-400"}>
                                  {pnl >= 0 ? "+" : ""}₹{pnl.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                </span>
                              ) : (
                                <span className="text-slate-500 text-xs">—</span>
                              )}
                            </div>
                            <div className="text-[10px] text-slate-500 mt-0.5 font-mono">
                              {isActual && retPct != null ? (
                                <span className={retPct >= 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                                  {retPct >= 0 ? "+" : ""}{retPct.toFixed(2)}%
                                </span>
                              ) : (
                                "Buy price required"
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Column 3: Forensic Risk Score & Actions */}
                        <div className="flex items-center justify-between lg:justify-end gap-4 shrink-0 border-t lg:border-t-0 border-white/[0.05] pt-4 lg:pt-0">
                          <div className="text-right">
                            <div className="text-2xl font-black font-mono text-white">
                              {holding.risk?.score ?? "—"}
                              <span className="text-xs font-normal text-slate-500"> /100</span>
                            </div>
                            <div className="text-[10px] text-slate-400 uppercase tracking-wider font-mono">
                              Dakota Risk
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => startEdit(holding)}
                              className="p-2 rounded-xl border border-white/[0.08] bg-white/[0.02] text-slate-400 hover:border-cyan-500/40 hover:bg-cyan-500/10 hover:text-cyan-300 transition"
                              title="Edit position or recorded purchase price"
                            >
                              <Edit3 className="w-4 h-4" />
                            </button>

                            <button
                              onClick={() => removeHolding(holding.ticker)}
                              className="p-2 rounded-xl border border-white/[0.08] bg-white/[0.02] text-slate-400 hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-300 transition"
                              title="Remove holding from portfolio"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </section>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: ADD & MANAGE POSITION */}
        {/* ========================================================================= */}
        {activeTab === "manage" && (
          <section className="space-y-8">
            <div className="rounded-2xl border border-white/[0.08] bg-[#0a0e17] shadow-xl p-6 sm:p-8">
              <div className="flex items-center justify-between gap-4 mb-6">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <Plus className="w-5 h-5 text-cyan-400" />
                    <span>{editingTicker ? `Edit Position: ${editingTicker}` : "Add Portfolio Holding"}</span>
                  </h2>
                  <p className="text-xs text-slate-400 mt-1 max-w-xl">
                    Register any stock from the Indian equity universe (NSE/BSE). Historical purchase price is optional — if omitted, the system reliably marks your position as Estimated Cost Basis using real-time quotes.
                  </p>
                </div>

                {editingTicker && (
                  <button
                    onClick={cancelEdit}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-white/[0.1] bg-white/[0.05] px-3 py-1.5 text-xs text-slate-300 hover:text-white transition"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>Cancel Edit</span>
                  </button>
                )}
              </div>

              {/* Quick suggestion chips */}
              <div className="mb-6">
                <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-2">
                  Popular Scrips (Click to Pre-fill):
                </div>
                <div className="flex flex-wrap gap-2">
                  {[
                    { ticker: "WIPRO", name: "Wipro Ltd", defaultQty: "15" },
                    { ticker: "ZOMATO", name: "Zomato Ltd", defaultQty: "100" },
                    { ticker: "RELIANCE", name: "Reliance Ind", defaultQty: "10" },
                    { ticker: "TCS", name: "Tata Consultancy", defaultQty: "5" },
                    { ticker: "INFY", name: "Infosys Ltd", defaultQty: "10" },
                    { ticker: "HDFCBANK", name: "HDFC Bank", defaultQty: "20" },
                    { ticker: "CLOUD", name: "Varanium Cloud", defaultQty: "13" },
                  ].map((s) => (
                    <button
                      key={s.ticker}
                      type="button"
                      onClick={() => selectQuickTicker(s.ticker, s.defaultQty)}
                      className={`rounded-lg border px-2.5 py-1 text-xs font-mono transition ${
                        ticker === s.ticker
                          ? "border-cyan-400 bg-cyan-500/20 text-cyan-200"
                          : "border-white/[0.08] bg-white/[0.02] text-slate-300 hover:border-cyan-500/40 hover:text-cyan-300"
                      }`}
                    >
                      <span className="font-bold">{s.ticker}</span>{" "}
                      <span className="text-[10px] text-slate-400">({s.name})</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Position Form */}
              <form onSubmit={addOrUpdateHolding} className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-3">
                  <div>
                    <label className="block text-xs font-mono uppercase tracking-wider text-slate-400 mb-1.5">
                      Ticker Symbol *
                    </label>
                    <input
                      value={ticker}
                      onChange={(e) => setTicker(e.target.value.toUpperCase())}
                      placeholder="e.g. WIPRO, ZOMATO"
                      required
                      className="w-full rounded-xl border border-white/[0.1] bg-black/50 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-600 focus:border-cyan-500/60 font-mono uppercase font-bold"
                    />
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      NSE listed ticker (or BSE scrip code)
                    </span>
                  </div>

                  <div>
                    <label className="block text-xs font-mono uppercase tracking-wider text-slate-400 mb-1.5">
                      Quantity of Shares *
                    </label>
                    <input
                      value={quantity}
                      onChange={(e) => setQuantity(e.target.value)}
                      type="number"
                      min="0.0001"
                      step="any"
                      placeholder="e.g. 15"
                      required
                      className="w-full rounded-xl border border-white/[0.1] bg-black/50 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-600 focus:border-cyan-500/60 font-mono"
                    />
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      Total shares currently held in account
                    </span>
                  </div>

                  <div>
                    <label className="block text-xs font-mono uppercase tracking-wider text-slate-400 mb-1.5 flex items-center justify-between">
                      <span>Avg Buy Price ₹</span>
                      <span className="text-[10px] text-cyan-400 font-normal">Optional</span>
                    </label>
                    <input
                      value={averagePrice}
                      onChange={(e) => setAveragePrice(e.target.value)}
                      type="number"
                      min="0"
                      step="any"
                      placeholder="e.g. 150.00 (Leave blank if unknown)"
                      className="w-full rounded-xl border border-white/[0.1] bg-black/50 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-600 focus:border-cyan-500/60 font-mono"
                    />
                    <span className="text-[10px] text-slate-500 mt-1 block">
                      If blank, marked as Estimated Cost Basis
                    </span>
                  </div>
                </div>

                <div className="pt-2 flex items-center gap-4">
                  <button
                    type="submit"
                    disabled={saving}
                    className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 px-6 py-3 text-sm font-bold text-white shadow-lg shadow-cyan-500/20 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50 transition font-mono"
                  >
                    {saving ? (
                      <span>Saving Position...</span>
                    ) : editingTicker ? (
                      <span>Update Position Details</span>
                    ) : (
                      <span>Add Position to Portfolio</span>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      cancelEdit();
                      setActiveTab("holdings");
                    }}
                    className="rounded-xl border border-white/[0.08] px-4 py-3 text-sm font-semibold text-slate-400 hover:text-white transition"
                  >
                    View Holdings
                  </button>
                </div>
              </form>
            </div>

            {/* Quick table of current positions for rapid management */}
            <div className="rounded-2xl border border-white/[0.08] bg-[#0a0e17] overflow-hidden">
              <div className="border-b border-white/[0.08] px-6 py-4 flex items-center justify-between">
                <h3 className="text-sm font-bold text-white font-mono uppercase tracking-wider">
                  Configured Positions Directory
                </h3>
                <span className="text-xs text-slate-400 font-mono">{totalPositions} Total</span>
              </div>

              <div className="divide-y divide-white/[0.04]">
                {portfolio?.holdings.map((h) => (
                  <div key={h.ticker} className="px-6 py-3.5 flex items-center justify-between text-xs font-mono">
                    <div className="flex items-center gap-3">
                      <span className="font-bold text-white text-sm">{h.ticker}</span>
                      <span className="text-slate-400">{h.name}</span>
                      <span className="text-slate-500">• {h.quantity} shares</span>
                      {h.average_buy_price != null ? (
                        <span className="text-emerald-400">@ ₹{h.average_buy_price}</span>
                      ) : (
                        <span className="text-amber-400 text-[11px]">(Unrecorded Buy Price)</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => startEdit(h)}
                        className="px-2.5 py-1 rounded-lg border border-white/[0.08] bg-white/[0.02] text-slate-300 hover:border-cyan-500/40 hover:text-cyan-300 transition"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => removeHolding(h.ticker)}
                        className="px-2.5 py-1 rounded-lg border border-white/[0.08] bg-white/[0.02] text-rose-400 hover:border-rose-500/40 hover:bg-rose-500/10 transition"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: RISK & EXPOSURE RADAR */}
        {/* ========================================================================= */}
        {activeTab === "radar" && (
          <section className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* High Risk Tier */}
              <div className="rounded-2xl border border-rose-500/30 bg-rose-500/5 p-6 shadow-xl">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-rose-400 font-bold font-mono text-sm">
                    <ShieldAlert className="w-5 h-5" />
                    <span>HIGH FORENSIC RISK</span>
                  </div>
                  <span className="rounded-full bg-rose-500/20 px-2 py-0.5 text-xs font-bold font-mono text-rose-300">
                    {highRiskPositions} Positions
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-2">
                  Scrips exhibiting active pump-and-dump signals, SEBI enforcement orders, promoter dumping, or GSM/ASM surveillance.
                </p>
                <div className="mt-4 pt-4 border-t border-rose-500/20 space-y-2">
                  {portfolio?.holdings
                    .filter((h) => h.risk?.band === "High")
                    .map((h) => (
                      <div key={h.ticker} className="flex items-center justify-between text-xs font-mono">
                        <Link href={`/stocks/${h.ticker}`} className="font-bold text-white hover:text-rose-300">
                          {h.ticker}
                        </Link>
                        <span className="text-rose-400 font-bold">{h.risk?.score}/100</span>
                      </div>
                    ))}
                  {highRiskPositions === 0 && (
                    <div className="text-xs text-slate-500">No high-risk positions detected.</div>
                  )}
                </div>
              </div>

              {/* Elevated Risk Tier */}
              <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-6 shadow-xl">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-amber-400 font-bold font-mono text-sm">
                    <AlertTriangle className="w-5 h-5" />
                    <span>ELEVATED CAUTION</span>
                  </div>
                  <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-bold font-mono text-amber-300">
                    {elevatedPositions} Positions
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-2">
                  Securities with moderate footprint anomalies, tip mentions, or minor financial concentration red flags.
                </p>
                <div className="mt-4 pt-4 border-t border-amber-500/20 space-y-2">
                  {portfolio?.holdings
                    .filter((h) => h.risk?.band === "Elevated")
                    .map((h) => (
                      <div key={h.ticker} className="flex items-center justify-between text-xs font-mono">
                        <Link href={`/stocks/${h.ticker}`} className="font-bold text-white hover:text-amber-300">
                          {h.ticker}
                        </Link>
                        <span className="text-amber-400 font-bold">{h.risk?.score}/100</span>
                      </div>
                    ))}
                  {elevatedPositions === 0 && (
                    <div className="text-xs text-slate-500">No elevated caution positions.</div>
                  )}
                </div>
              </div>

              {/* Safe Tier */}
              <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-6 shadow-xl">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-emerald-400 font-bold font-mono text-sm">
                    <ShieldCheck className="w-5 h-5" />
                    <span>LOW RISK / CLEAN</span>
                  </div>
                  <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-bold font-mono text-emerald-300">
                    {lowRiskPositions} Positions
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-2">
                  Equities with clean shareholding history, deep market float, and no anomalous syndicate promotion.
                </p>
                <div className="mt-4 pt-4 border-t border-emerald-500/20 space-y-2">
                  {portfolio?.holdings
                    .filter((h) => h.risk?.band === "Low")
                    .map((h) => (
                      <div key={h.ticker} className="flex items-center justify-between text-xs font-mono">
                        <Link href={`/stocks/${h.ticker}`} className="font-bold text-white hover:text-emerald-300">
                          {h.ticker}
                        </Link>
                        <span className="text-emerald-400 font-bold">{h.risk?.score}/100</span>
                      </div>
                    ))}
                  {lowRiskPositions === 0 && (
                    <div className="text-xs text-slate-500">No low-risk positions recorded.</div>
                  )}
                </div>
              </div>
            </div>

            {/* Forensic Detail Stream */}
            <div className="rounded-2xl border border-white/[0.08] bg-[#0a0e17] p-6 shadow-xl">
              <h3 className="text-base font-bold text-white mb-2 flex items-center gap-2">
                <Info className="w-4 h-4 text-cyan-400" />
                <span>Active Forensic Signals Across Portfolio</span>
              </h3>
              <p className="text-xs text-slate-400 mb-6">
                Aggregated forensic reasons identified across your registered holdings by the Dakota Intelligence engine.
              </p>

              <div className="grid gap-3 sm:grid-cols-2">
                {portfolio?.holdings.map((h) => {
                  const reasons = h.risk?.reasons || [];
                  if (reasons.length === 0) return null;

                  return (
                    <div
                      key={h.ticker}
                      className="rounded-xl border border-white/[0.05] bg-white/[0.02] p-4 space-y-2"
                    >
                      <div className="flex items-center justify-between font-mono">
                        <span className="font-bold text-white">{h.ticker} ({h.name})</span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${riskClass(h.risk?.band)}`}>
                          {h.risk?.band}
                        </span>
                      </div>
                      <ul className="text-xs text-slate-400 space-y-1 list-disc list-inside">
                        {reasons.slice(0, 4).map((r, i) => (
                          <li key={i} className="text-[11px] leading-relaxed">
                            {r}
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </div>

              <div className="mt-6 pt-4 border-t border-white/[0.06] flex items-center justify-between">
                <span className="text-xs text-slate-400 font-mono">
                  Want full automated risk scanning and live alerting?
                </span>
                <Link
                  href="/watcher"
                  className="inline-flex items-center gap-1.5 text-xs font-bold text-cyan-400 hover:text-cyan-300 font-mono"
                >
                  <span>Open Portfolio Watcher</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          </section>
        )}
      </div>

      {/* Terminal Footer */}
      <footer className="border-t border-white/[0.08] bg-[#070b12] py-6 text-center text-xs text-slate-500 font-mono">
        DAKOTA FINANCIAL INTELLIGENCE TERMINAL • VALUATION &amp; RISK SURVEILLANCE • NOT INVESTMENT ADVICE
      </footer>
    </main>
  );
}