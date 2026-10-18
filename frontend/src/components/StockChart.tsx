"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import {
  ComposedChart,
  Area,
  Line,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import TechnicalSignals from "./TechnicalSignals";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ChartPoint = {
  date: string;
  timestamp?: string;
  close: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  is_up?: boolean;
  ema_20?: number | null;
  sma_50?: number | null;
  sma_200?: number | null;
  bb_upper?: number | null;
  bb_mid?: number | null;
  bb_lower?: number | null;
  supertrend?: number | null;
  supertrend_dir?: number;
  supertrend_bull?: number | null;
  supertrend_bear?: number | null;
};

type OverlaysLatest = {
  ema_20?: number | null;
  sma_50?: number | null;
  sma_200?: number | null;
  bb_upper?: number | null;
  bb_mid?: number | null;
  bb_lower?: number | null;
  supertrend?: number | null;
  supertrend_dir?: number;
};

type ChartResponse = {
  ticker: string;
  period: string;
  interval?: string;
  is_intraday?: boolean;
  is_market_open?: boolean;
  session_status?: string;
  market_time_ist?: string;
  last_traded_at?: string;
  session_date?: string;
  latest_price: number | null;
  prev_close?: number | null;
  day_open?: number | null;
  day_high?: number | null;
  day_low?: number | null;
  day_volume?: number | null;
  change: number;
  change_pct: number;
  high_52w: number | null;
  low_52w: number | null;
  avg_volume: number;
  overlays_latest?: OverlaysLatest;
  points: ChartPoint[];
};

type StockChartProps = {
  ticker?: string;
  data?: any[];
  stockName?: string;
  riskInfo?: {
    score: number | null;
    band: string;
    verdict?: string;
  };
  onClose?: () => void;
  showDetailsLink?: boolean;
};

type Period = "1d" | "1m" | "3m" | "6m" | "1y" | "all";
export type IntradayInterval = "1m" | "3m" | "5m" | "10m" | "30m" | "1h";

export const INTRADAY_INTERVALS: { label: string; value: IntradayInterval; title: string }[] = [
  { label: "1 min", value: "1m", title: "1 Minute Live Candles" },
  { label: "3 min", value: "3m", title: "3 Minute Live Candles" },
  { label: "5 min", value: "5m", title: "5 Minute Live Candles" },
  { label: "10 min", value: "10m", title: "10 Minute Live Candles" },
  { label: "30 min", value: "30m", title: "30 Minute Live Candles" },
  { label: "1 hour", value: "1h", title: "1 Hour Live Candles" },
];

export default function StockChart({
  ticker = "",
  data: initialData,
  stockName,
  riskInfo,
  onClose,
  showDetailsLink = true,
}: StockChartProps) {
  const [period, setPeriod] = useState<Period>("1d");
  const [interval, setIntradayInterval] = useState<IntradayInterval>("5m");
  const [data, setData] = useState<ChartResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Live Auto-Refresh State
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [countdown, setCountdown] = useState(10);
  const [priceFlash, setPriceFlash] = useState<"up" | "down" | null>(null);
  const prevPriceRef = useRef<number | null>(null);

  // Technical Overlay Toggles
  const [showEma20, setShowEma20] = useState(false);
  const [showSma50, setShowSma50] = useState(false);
  const [showSma200, setShowSma200] = useState(false);
  const [showBollinger, setShowBollinger] = useState(false);
  const [showSupertrend, setShowSupertrend] = useState(false);
  const [showVolume, setShowVolume] = useState(true);
  const [showTechnicals, setShowTechnicals] = useState(false);

  // Price Flash on Change
  useEffect(() => {
    if (data?.latest_price != null && prevPriceRef.current != null) {
      if (data.latest_price > prevPriceRef.current) {
        setPriceFlash("up");
        const t = setTimeout(() => setPriceFlash(null), 900);
        return () => clearTimeout(t);
      } else if (data.latest_price < prevPriceRef.current) {
        setPriceFlash("down");
        const t = setTimeout(() => setPriceFlash(null), 900);
        return () => clearTimeout(t);
      }
    }
    prevPriceRef.current = data?.latest_price ?? null;
  }, [data?.latest_price]);

  // Primary Fetch Function
  async function fetchChart(showSpinner = true, targetInterval?: IntradayInterval) {
    if (!ticker) return;
    const activeInterval = targetInterval || interval;
    if (showSpinner) {
      setLoading(true);
      setError("");
    }
    try {
      const res = await fetch(
        `${API}/api/stocks/${encodeURIComponent(ticker)}/chart?period=${period}&interval=${activeInterval}`,
        { cache: "no-store" }
      );
      if (!res.ok) {
        throw new Error(`Failed to load chart (HTTP ${res.status})`);
      }
      const json: ChartResponse = await res.json();
      setData(json);
      setCountdown(10);
    } catch (err) {
      if (showSpinner) {
        setError(err instanceof Error ? err.message : "Error loading chart data");
      }
    } finally {
      if (showSpinner) {
        setLoading(false);
      }
    }
  }

  // Initial load & period / interval changes
  useEffect(() => {
    if (!ticker && initialData && initialData.length > 0) {
      setData({
        ticker: "Stock",
        period: "1m",
        latest_price: initialData[initialData.length - 1]?.close ?? null,
        change: 0,
        change_pct: 0,
        high_52w: null,
        low_52w: null,
        avg_volume: 0,
        points: initialData.map((d: any) => ({
          date: d.date || "",
          close: Number(d.close) || 0,
          open: Number(d.open || d.close) || 0,
          high: Number(d.high || d.close) || 0,
          low: Number(d.low || d.close) || 0,
          volume: Number(d.volume) || 0,
          is_up: (Number(d.close) || 0) >= (Number(d.open || d.close) || 0),
          ema_20: d.ema_20 ? Number(d.ema_20) : null,
          sma_50: d.sma_50 ? Number(d.sma_50) : null,
          sma_200: d.sma_200 ? Number(d.sma_200) : null,
          bb_upper: d.bb_upper ? Number(d.bb_upper) : null,
          bb_mid: d.bb_mid ? Number(d.bb_mid) : null,
          bb_lower: d.bb_lower ? Number(d.bb_lower) : null,
          supertrend: d.supertrend ? Number(d.supertrend) : null,
          supertrend_dir: d.supertrend_dir ?? 1,
          supertrend_bull: d.supertrend_dir === 1 ? Number(d.supertrend) : null,
          supertrend_bear: d.supertrend_dir === -1 ? Number(d.supertrend) : null,
        })),
      });
      setLoading(false);
      return;
    }

    if (ticker) {
      fetchChart(true);
    }
  }, [ticker, period, interval]);

  // Live Auto-Refresh Polling Loop (Only on 1D timeframe)
  useEffect(() => {
    if (period !== "1d" || !autoRefresh || !ticker) return;

    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          fetchChart(false);
          return 10;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [period, interval, autoRefresh, ticker]);


  const isUp = (data?.change ?? 0) >= 0;
  const strokeColor = isUp ? "#10b981" : "#f43f5e";
  const gradientId = `chartGradient_${ticker}_${period}`;

  const maxVolume = Math.max(...(data?.points?.map((p) => p.volume) || [1]), 1);
  const latestPoint = data?.points && data.points.length > 0 ? data.points[data.points.length - 1] : null;

  function formatPrice(val: number | null | undefined) {
    if (val == null) return "—";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(val);
  }

  function formatCompactNumber(num: number | null | undefined) {
    if (num == null) return "—";
    if (num >= 10_000_000) return `${(num / 10_000_000).toFixed(2)} Cr`;
    if (num >= 100_000) return `${(num / 100_000).toFixed(2)} L`;
    if (num >= 1_000) return `${(num / 1_000).toFixed(1)}k`;
    return num.toLocaleString();
  }

  function bandBadgeClass(band?: string) {
    if (band === "High") return "border-red-500/30 bg-red-500/10 text-red-400";
    if (band === "Elevated") return "border-amber-500/30 bg-amber-500/10 text-amber-400";
    if (band === "Low") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
    return "border-zinc-700 bg-zinc-800 text-zinc-400";
  }

  return (
    <div className="relative overflow-hidden rounded-2xl border border-sky-500/30 bg-[#090d16] p-6 shadow-2xl backdrop-blur-xl transition-all">
      {/* Background ambient glow */}
      <div
        className="pointer-events-none absolute -top-24 -left-24 h-64 w-64 rounded-full blur-3xl opacity-20"
        style={{ backgroundColor: strokeColor }}
      />

      {/* Top Header */}
      <div className="relative z-10 flex flex-wrap items-start justify-between gap-4 border-b border-white/10 pb-5">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-2xl font-bold tracking-tight text-white">{ticker}</span>
            {stockName && <span className="text-sm font-medium text-white/50">{stockName}</span>}
            {riskInfo && (
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-0.5 text-xs font-semibold ${bandBadgeClass(
                  riskInfo.band
                )}`}
              >
                <span>Risk: {riskInfo.score != null ? `${riskInfo.score}/100` : "—"}</span>
                <span className="opacity-75">({riskInfo.band})</span>
              </span>
            )}
          </div>

          <div className="mt-2 flex flex-wrap items-baseline gap-3">
            {/* Price with Live Flash highlight */}
            <span
              className={`text-3xl font-extrabold tracking-tight transition-all duration-300 ${
                priceFlash === "up"
                  ? "text-emerald-400 bg-emerald-500/20 px-1 rounded scale-105"
                  : priceFlash === "down"
                  ? "text-rose-400 bg-rose-500/20 px-1 rounded scale-105"
                  : "text-white"
              }`}
            >
              {formatPrice(data?.latest_price)}
            </span>
            {data?.latest_price != null && (
              <span
                className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-sm font-semibold ${
                  isUp ? "bg-emerald-500/15 text-emerald-400" : "bg-rose-500/15 text-rose-400"
                }`}
              >
                {isUp ? "▲ +" : "▼ "}
                {Math.abs(data.change).toFixed(2)} ({isUp ? "+" : ""}
                {data.change_pct.toFixed(2)}%)
              </span>
            )}
            <span className="text-xs text-white/40">
              {data?.is_intraday ? "NSE Real-time Intraday" : "Real Exchange History"}
            </span>
          </div>
        </div>

        {/* Timeframe selector, Indicators toggle & Actions */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Timeframe pills including 1D LIVE */}
          <div className="flex items-center rounded-lg border border-white/10 bg-white/[0.03] p-1">
            {/* 1D LIVE Tab */}
            <button
              onClick={() => setPeriod("1d")}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-bold transition ${
                period === "1d"
                  ? "bg-emerald-500/25 text-emerald-300 border border-emerald-400/40 shadow-sm shadow-emerald-500/20"
                  : "text-white/45 hover:text-white"
              }`}
            >
              <span
                className={`inline-block h-1.5 w-1.5 rounded-full ${
                  data?.is_market_open
                    ? "bg-emerald-400 animate-pulse"
                    : "bg-emerald-500/60"
                }`}
              />
              <span>1D LIVE</span>
            </button>

            {(["1m", "3m", "6m", "1y", "all"] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                  period === p
                    ? "bg-sky-500/20 text-sky-300 shadow-sm"
                    : "text-white/45 hover:text-white"
                }`}
              >
                {p.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Intraday Time Resolution Pills: 1 min, 3 min, 5 min, 10 min, 30 min, 1 hour */}
          <div className="flex items-center gap-1 rounded-lg border border-sky-500/25 bg-[#070e1b] p-1 shadow-sm">
            <span className="hidden sm:inline-block px-1.5 text-[10px] font-mono font-bold tracking-wider text-sky-400 uppercase">
              Time:
            </span>
            {INTRADAY_INTERVALS.map((iv) => {
              const isSelected = period === "1d" && interval === iv.value;
              return (
                <button
                  key={iv.value}
                  onClick={() => {
                    if (period !== "1d") setPeriod("1d");
                    setIntradayInterval(iv.value);
                  }}
                  title={iv.title}
                  className={`rounded px-2 py-0.5 text-xs font-mono font-bold transition duration-150 ${
                    isSelected
                      ? "bg-sky-400 text-slate-950 shadow-md shadow-sky-400/30 scale-105"
                      : "text-zinc-400 hover:text-white hover:bg-white/10"
                  }`}
                >
                  {iv.label}
                </button>
              );
            })}
          </div>

          {/* Technical overlays pills */}
          <div className="flex flex-wrap items-center gap-1 rounded-lg border border-white/10 bg-white/[0.02] p-1">
            <button
              onClick={() => setShowEma20(!showEma20)}
              title="20-period Exponential Moving Average"
              className={`rounded-md px-2 py-1 text-[11px] font-semibold transition ${
                showEma20
                  ? "border border-amber-500/50 bg-amber-500/20 text-amber-300 shadow-sm shadow-amber-500/10"
                  : "text-white/45 hover:text-white"
              }`}
            >
              20 EMA
            </button>

            <button
              onClick={() => setShowSma50(!showSma50)}
              title="50-period Simple Moving Average"
              className={`rounded-md px-2 py-1 text-[11px] font-semibold transition ${
                showSma50
                  ? "border border-sky-400/50 bg-sky-500/20 text-sky-300 shadow-sm shadow-sky-500/10"
                  : "text-white/45 hover:text-white"
              }`}
            >
              50 SMA
            </button>

            <button
              onClick={() => setShowSma200(!showSma200)}
              title="200-period Simple Moving Average"
              className={`rounded-md px-2 py-1 text-[11px] font-semibold transition ${
                showSma200
                  ? "border border-fuchsia-500/50 bg-fuchsia-500/20 text-fuchsia-300 shadow-sm shadow-fuchsia-500/10"
                  : "text-white/45 hover:text-white"
              }`}
            >
              200 SMA
            </button>

            <button
              onClick={() => setShowBollinger(!showBollinger)}
              title="Bollinger Bands (20, 2)"
              className={`rounded-md px-2 py-1 text-[11px] font-semibold transition ${
                showBollinger
                  ? "border border-purple-400/50 bg-purple-500/20 text-purple-300 shadow-sm shadow-purple-500/10"
                  : "text-white/45 hover:text-white"
              }`}
            >
              BB (20,2)
            </button>

            <button
              onClick={() => setShowSupertrend(!showSupertrend)}
              title="Supertrend (10, 3 ATR Trailing Stop)"
              className={`rounded-md px-2 py-1 text-[11px] font-semibold transition ${
                showSupertrend
                  ? "border border-emerald-400/50 bg-emerald-500/20 text-emerald-300 shadow-sm shadow-emerald-500/10"
                  : "text-white/45 hover:text-white"
              }`}
            >
              Supertrend
            </button>

            <button
              onClick={() => setShowVolume(!showVolume)}
              title="Volume Bars Overlay"
              className={`rounded-md px-2 py-1 text-[11px] font-semibold transition ${
                showVolume
                  ? "border border-teal-400/50 bg-teal-500/20 text-teal-300 shadow-sm shadow-teal-500/10"
                  : "text-white/45 hover:text-white"
              }`}
            >
              Volume
            </button>
          </div>

          {/* Technical Consensus Toggle */}
          <button
            onClick={() => setShowTechnicals(!showTechnicals)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
              showTechnicals
                ? "border-emerald-500/50 bg-emerald-500/20 text-emerald-300 shadow-lg shadow-emerald-500/10"
                : "border-sky-500/30 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20"
            }`}
          >
            <span>⚡ Technical Signals</span>
            <span>{showTechnicals ? "▲" : "▼"}</span>
          </button>

          {showDetailsLink && (
            <Link
              href={`/stocks/${ticker}`}
              className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-semibold text-white/70 transition hover:border-sky-400/40 hover:bg-white/[0.08] hover:text-white"
            >
              Full Analysis →
            </Link>
          )}

          {onClose && (
            <button
              onClick={onClose}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-xs text-white/50 transition hover:bg-white/10 hover:text-white"
              title="Close chart"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Intraday Live Market Session Status Banner */}
      {period === "1d" && data?.is_intraday && (
        <div className="relative z-10 flex flex-wrap items-center justify-between gap-3 border-b border-white/5 py-3 text-xs">
          <div className="flex flex-wrap items-center gap-2.5">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-semibold text-[11px] ${
                data.is_market_open
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                  : "bg-amber-500/15 text-amber-300 border border-amber-500/30"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  data.is_market_open
                    ? "bg-emerald-400 animate-pulse"
                    : "bg-amber-400"
                }`}
              />
              <span>{data.session_status || "Live Exchange Feed"}</span>
            </span>

            {/* Active resolution badge */}
            <span className="inline-flex items-center gap-1.5 rounded-md border border-sky-500/30 bg-sky-500/10 px-2.5 py-0.5 font-mono text-[11px] text-sky-300 font-semibold">
              <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
              <span>{interval.toUpperCase()} Live Candlesticks</span>
              <span className="text-sky-400/60 font-normal">({data.points?.length ?? 0} bars)</span>
            </span>

            {data.last_traded_at && (
              <span className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.04] px-2.5 py-0.5 font-mono text-[11px] text-white/70">
                <span className="text-white/40">Last Traded:</span>
                <span className="font-semibold text-white">{data.last_traded_at}</span>
              </span>
            )}
          </div>

          {/* Real-time sync controls */}
          <div className="flex items-center gap-2.5">
            {autoRefresh && (
              <span className="flex items-center gap-1 text-[11px] text-white/40">
                <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-ping" />
                Live sync in <span className="font-mono text-sky-300 font-bold">{countdown}s</span>
              </span>
            )}

            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition ${
                autoRefresh
                  ? "border border-sky-400/30 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20"
                  : "border border-white/10 bg-white/5 text-white/40 hover:text-white"
              }`}
            >
              {autoRefresh ? "Pause 10s Sync" : "Resume 10s Sync"}
            </button>
          </div>
        </div>
      )}

      {/* Metrics Row (Intraday vs Historical) */}
      <div className="relative z-10 my-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {data?.is_intraday ? (
          <>
            <div className="rounded-xl border border-white/5 bg-white/[0.02] p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-white/40">Day Open</div>
              <div className="mt-0.5 text-sm font-semibold text-white/90">
                {formatPrice(data.day_open ?? data.prev_close)}
              </div>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.02] p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-white/40">Day High / Low</div>
              <div className="mt-0.5 text-sm font-semibold text-white/90">
                ₹{data.day_high?.toFixed(2) ?? "—"} / ₹{data.day_low?.toFixed(2) ?? "—"}
              </div>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.02] p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-white/40">Today Volume</div>
              <div className="mt-0.5 text-sm font-semibold text-white/90">
                {formatCompactNumber(data.day_volume)}
              </div>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.02] p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-white/40">Active Overlays</div>
              <div className="mt-0.5 flex flex-wrap gap-1 text-[11px] font-medium leading-relaxed">
                {showEma20 && <span className="text-amber-400 mr-1.5">● 20 EMA: ₹{latestPoint?.ema_20?.toFixed(1) ?? "—"}</span>}
                {showSma50 && <span className="text-sky-400 mr-1.5">● 50 SMA: ₹{latestPoint?.sma_50?.toFixed(1) ?? "—"}</span>}
                {showBollinger && <span className="text-purple-300 mr-1.5">● BB</span>}
                {showSupertrend && (
                  <span className={latestPoint?.supertrend_dir === 1 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                    ● ST ({latestPoint?.supertrend_dir === 1 ? "BULL" : "BEAR"})
                  </span>
                )}
                {!showEma20 && !showSma50 && !showBollinger && !showSupertrend && (
                  <span className="text-white/40">None selected</span>
                )}
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="rounded-xl border border-white/5 bg-white/[0.02] p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-white/40">52W High</div>
              <div className="mt-0.5 text-sm font-semibold text-white/90">
                {formatPrice(data?.high_52w)}
              </div>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.02] p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-white/40">52W Low</div>
              <div className="mt-0.5 text-sm font-semibold text-white/90">
                {formatPrice(data?.low_52w)}
              </div>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.02] p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-white/40">Avg Volume (52W)</div>
              <div className="mt-0.5 text-sm font-semibold text-white/90">
                {formatCompactNumber(data?.avg_volume)}
              </div>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.02] p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-white/40">Active Overlays</div>
              <div className="mt-0.5 flex flex-wrap gap-1 text-[11px] font-medium leading-relaxed">
                {showEma20 && <span className="text-amber-400 mr-1.5">● 20 EMA: ₹{latestPoint?.ema_20?.toFixed(1) ?? "—"}</span>}
                {showSma50 && <span className="text-sky-400 mr-1.5">● 50 SMA: ₹{latestPoint?.sma_50?.toFixed(1) ?? "—"}</span>}
                {showSma200 && <span className="text-fuchsia-400 mr-1.5">● 200 SMA</span>}
                {showBollinger && <span className="text-purple-300 mr-1.5">● BB</span>}
                {showSupertrend && (
                  <span className={latestPoint?.supertrend_dir === 1 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                    ● ST ({latestPoint?.supertrend_dir === 1 ? "BULL" : "BEAR"})
                  </span>
                )}
                {!showEma20 && !showSma50 && !showSma200 && !showBollinger && !showSupertrend && (
                  <span className="text-white/40">None selected</span>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Chart Canvas */}
      <div className="relative z-10 h-72 w-full pt-2">
        {loading && (
          <div className="flex h-full w-full items-center justify-center rounded-xl bg-white/[0.01]">
            <div className="flex items-center gap-3 text-sm text-sky-400">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
              Loading {ticker} price series...
            </div>
          </div>
        )}

        {error && (
          <div className="flex h-full w-full items-center justify-center rounded-xl bg-rose-500/[0.05] text-sm text-rose-400">
            {error}
          </div>
        )}

        {!loading && !error && data && data.points.length > 0 && (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data.points} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={strokeColor} stopOpacity={0.35} />
                  <stop offset="95%" stopColor={strokeColor} stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff0a" vertical={false} />
              <XAxis
                dataKey="date"
                stroke="#ffffff25"
                tick={{ fill: "#ffffff50", fontSize: 11 }}
                minTickGap={35}
                tickFormatter={(val: string) => {
                  if (data.is_intraday) {
                    return val; // "09:15", "10:30", "15:15"
                  }
                  try {
                    const parts = val.split("-");
                    if (parts.length >= 3) {
                      return `${parts[2]}/${parts[1]}`;
                    }
                    return val;
                  } catch {
                    return val;
                  }
                }}
              />
              {/* Primary Price Axis */}
              <YAxis
                yAxisId="price"
                stroke="#ffffff25"
                tick={{ fill: "#ffffff50", fontSize: 11 }}
                domain={["auto", "auto"]}
                orientation="right"
                tickFormatter={(val: number) => `₹${val.toFixed(0)}`}
              />
              {/* Secondary Volume Axis */}
              <YAxis
                yAxisId="volume"
                domain={[0, maxVolume * 3.6]}
                orientation="left"
                hide={true}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const pt = payload[0].payload as ChartPoint;
                    return (
                      <div className="rounded-xl border border-white/10 bg-[#0d131f]/95 p-3 shadow-2xl backdrop-blur-md">
                        <div className="text-[11px] font-medium text-white/50">
                          {data.is_intraday ? `Time: ${pt.date} IST • ${interval.toUpperCase()} Candle` : `Date: ${pt.date}`}
                        </div>
                        <div className="mt-1 flex items-baseline gap-2">
                          <span className="text-base font-bold text-white">
                            ₹{pt.close.toFixed(2)}
                          </span>
                          <span
                            className={
                              pt.close >= pt.open
                                ? "text-xs font-semibold text-emerald-400"
                                : "text-xs font-semibold text-rose-400"
                            }
                          >
                            {pt.close >= pt.open ? "▲" : "▼"}{" "}
                            {(((pt.close - pt.open) / (pt.open || 1)) * 100).toFixed(2)}%
                          </span>
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-white/10 pt-1.5 text-[10px] text-white/60">
                          <div>
                            Open: <span className="text-white/80">₹{pt.open.toFixed(2)}</span>
                          </div>
                          <div>
                            High: <span className="text-white/80">₹{pt.high.toFixed(2)}</span>
                          </div>
                          <div>
                            Low: <span className="text-white/80">₹{pt.low.toFixed(2)}</span>
                          </div>
                          <div>
                            Vol: <span className="text-white/80">{formatCompactNumber(pt.volume)}</span>
                          </div>
                          {showEma20 && pt.ema_20 && (
                            <div>
                              20 EMA: <span className="text-amber-400">₹{pt.ema_20.toFixed(2)}</span>
                            </div>
                          )}
                          {showSma50 && pt.sma_50 && (
                            <div>
                              50 SMA: <span className="text-sky-400">₹{pt.sma_50.toFixed(2)}</span>
                            </div>
                          )}
                          {showSma200 && pt.sma_200 && (
                            <div>
                              200 SMA: <span className="text-fuchsia-400">₹{pt.sma_200.toFixed(2)}</span>
                            </div>
                          )}
                          {showBollinger && pt.bb_upper && (
                            <div>
                              BB Upper: <span className="text-purple-300">₹{pt.bb_upper.toFixed(2)}</span>
                            </div>
                          )}
                          {showBollinger && pt.bb_lower && (
                            <div>
                              BB Lower: <span className="text-purple-300">₹{pt.bb_lower.toFixed(2)}</span>
                            </div>
                          )}
                          {showSupertrend && pt.supertrend && (
                            <div className="col-span-2">
                              Supertrend:{" "}
                              <span
                                className={
                                  pt.supertrend_dir === 1
                                    ? "font-semibold text-emerald-400"
                                    : "font-semibold text-rose-400"
                                }
                              >
                                ₹{pt.supertrend.toFixed(2)} ({pt.supertrend_dir === 1 ? "BULL" : "BEAR"})
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  }
                  return null;
                }}
              />

              {/* Volume Bars at Bottom */}
              {showVolume && (
                <Bar yAxisId="volume" dataKey="volume" isAnimationActive={false} maxBarSize={7}>
                  {data.points.map((pt, i) => (
                    <Cell
                      key={`vol-bar-${i}`}
                      fill={pt.close >= pt.open ? "#10b981" : "#f43f5e"}
                      fillOpacity={0.25}
                    />
                  ))}
                </Bar>
              )}

              {/* Main Close Price Area */}
              <Area
                yAxisId="price"
                type="monotone"
                dataKey="close"
                stroke={strokeColor}
                strokeWidth={2}
                fillOpacity={1}
                fill={`url(#${gradientId})`}
                name="Close Price"
              />

              {/* 20 EMA */}
              {showEma20 && (
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey="ema_20"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                  name="20 EMA"
                />
              )}

              {/* 50 SMA */}
              {showSma50 && (
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey="sma_50"
                  stroke="#38bdf8"
                  strokeWidth={1.5}
                  dot={false}
                  strokeDasharray="4 4"
                  isAnimationActive={false}
                  name="50 SMA"
                />
              )}

              {/* 200 SMA */}
              {showSma200 && (
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey="sma_200"
                  stroke="#e879f9"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                  name="200 SMA"
                />
              )}

              {/* Bollinger Bands */}
              {showBollinger && (
                <>
                  <Line
                    yAxisId="price"
                    type="monotone"
                    dataKey="bb_upper"
                    stroke="#c084fc"
                    strokeWidth={1.2}
                    strokeDasharray="3 3"
                    dot={false}
                    isAnimationActive={false}
                    name="BB Upper"
                  />
                  <Line
                    yAxisId="price"
                    type="monotone"
                    dataKey="bb_mid"
                    stroke="#818cf8"
                    strokeWidth={1}
                    strokeDasharray="2 2"
                    dot={false}
                    isAnimationActive={false}
                    name="BB Mid (20 SMA)"
                  />
                  <Line
                    yAxisId="price"
                    type="monotone"
                    dataKey="bb_lower"
                    stroke="#c084fc"
                    strokeWidth={1.2}
                    strokeDasharray="3 3"
                    dot={false}
                    isAnimationActive={false}
                    name="BB Lower"
                  />
                </>
              )}

              {/* Supertrend (10, 3 ATR) */}
              {showSupertrend && (
                <>
                  <Line
                    yAxisId="price"
                    type="monotone"
                    dataKey="supertrend_bull"
                    stroke="#10b981"
                    strokeWidth={2.2}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                    name="Supertrend (Bull)"
                  />
                  <Line
                    yAxisId="price"
                    type="monotone"
                    dataKey="supertrend_bear"
                    stroke="#f43f5e"
                    strokeWidth={2.2}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                    name="Supertrend (Bear)"
                  />
                </>
              )}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>

      {riskInfo?.verdict && (
        <div className="relative z-10 mt-4 rounded-xl border border-white/5 bg-white/[0.02] p-3 text-xs text-white/60">
          <span className="font-semibold text-white/80">Dakota Risk Assessment: </span>
          {riskInfo.verdict}
        </div>
      )}

      {/* Expandable Technical Signals Panel */}
      {showTechnicals && ticker && (
        <div className="relative z-10 mt-6 border-t border-white/10 pt-6">
          <TechnicalSignals ticker={ticker} tipMarkers={riskInfo?.band === "High" ? 3 : 0} />
        </div>
      )}
    </div>
  );
}
