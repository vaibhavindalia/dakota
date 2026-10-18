"use client";

import { useState } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import RiskRing from "@/components/RiskRing";
import MarketBadges from "@/components/MarketBadges";
import StockChart from "@/components/StockChart";
import { 
  ShieldAlert, 
  Sparkles, 
  AlertTriangle, 
  CheckCircle2, 
  TrendingUp, 
  Send, 
  FileText, 
  ArrowRight,
  ExternalLink,
  Info,
  Clock,
  Layers,
  BarChart3
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ParsedTip = {
  clean_text?: string;
  tickers?: string[];
  price_target?: number | null;
  markers_found?: Record<string, string[]>;
  n_scam_markers?: number;
  urgency?: boolean;
  sebi_reg_claimed?: boolean;
  sebi_reg_number?: string | null;
  sebi_reg_verified?: boolean | null;
  fingerprint?: string;
  is_index?: boolean;
  index_name?: string | null;
};

type StockVerdict = {
  ticker: string;
  as_of?: string;
  score: number;
  band: string;
  verdict: string;
  contributions?: Record<string, number>;
  contribution_labels?: Record<string, string>;
  reasons?: string[];
  market?: any;
  next_steps?: string[];
};

type TipResult = {
  parsed?: ParsedTip;
  stock_verdicts?: StockVerdict[];
  headline?: string;
  tip_level_reasons?: string[];
  combined_reasons?: string[];
  market?: any;
  next_steps?: string[];
  disclaimer?: string;
};

const SAMPLE_TIPS = [
  {
    label: "🔥 WhatsApp Pump Tip",
    ticker: "VARANIUM",
    text: "URGENT BUY VARANIUM TARGET ₹500. Guaranteed 300% returns in 3 days. SEBI REG: INH000008912. Buy before upper circuit locks! VIP call.",
  },
  {
    label: "⚡ Operator Cartel Tip",
    ticker: "ZOMATO",
    text: "SURE SHOT BUY ZOMATO CMP 265 TARGET 350. Heavy insider operator buying confirmed by cartel syndicate. 100% jackpot call today.",
  },
  {
    label: "📈 SME Breakout Call",
    ticker: "BASILIC",
    text: "STRONG BUY BASILIC FLY TARGET 320 SL 210. Big FII block deal taking place at market open. Don't miss this multibagger!",
  },
];

export default function Home() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<TipResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function analyzeTip(overrideText?: string) {
    const tipToAnalyze = (overrideText ?? text).trim();
    if (!tipToAnalyze) {
      setError("Please paste a stock tip first.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch(`${API}/api/tip/check`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          tip: tipToAnalyze,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.detail || "Dakota could not analyze this tip.");
      }

      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  function handlePresetClick(sampleText: string) {
    setText(sampleText);
    analyzeTip(sampleText);
  }

  const stock = result?.stock_verdicts?.[0];
  const parsed = result?.parsed;

  return (
    <main className="min-h-screen bg-[#05070a] text-slate-100 flex flex-col bg-terminal-grid">
      <Navbar />

      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 sm:py-12 flex-1">
        {/* Terminal Header & Intelligence Brief */}
        <header className="mb-10">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/[0.08] pb-8">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-mono font-semibold text-cyan-300 mb-4">
                <ShieldAlert className="h-3.5 w-3.5" />
                <span>FORENSIC TIP INGESTION & RISK RADAR</span>
              </div>
              <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-white">
                Dakota Intelligence Core
              </h1>
              <p className="mt-3 max-w-2xl text-base text-slate-400">
                Forward unsolicited tips. Screen promoter &amp; operator footprint. Trace market cartels across 2,615+ Indian equities with institutional forensic rigor.
              </p>
            </div>

            {/* Quick Metrics Bar */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 shrink-0">
              <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-3">
                <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">Monitored Universe</div>
                <div className="text-lg font-bold font-mono text-white mt-0.5">2,615 Equities</div>
                <div className="text-[10px] text-emerald-400 flex items-center gap-1 mt-0.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
                  NSE &amp; BSE Pre-Computed
                </div>
              </div>

              <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-3">
                <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">Syndicates Mapped</div>
                <div className="text-lg font-bold font-mono text-cyan-300 mt-0.5">77 Channels</div>
                <div className="text-[10px] text-cyan-400/80">Copy-Paste Ratios Tracked</div>
              </div>

              <div className="col-span-2 sm:col-span-1 rounded-xl border border-white/[0.08] bg-white/[0.02] p-3">
                <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400">Surveillance Model</div>
                <div className="text-lg font-bold font-mono text-emerald-400 mt-0.5">SEBI ASM/GSM</div>
                <div className="text-[10px] text-slate-400">5-Pillar Score Authority</div>
              </div>
            </div>
          </div>
        </header>

        {/* Central Dakota AI Copilot Spotlight */}
        <section className="mb-8 rounded-2xl border border-cyan-500/30 bg-gradient-to-r from-[#071322] via-[#09152b] to-[#071322] p-6 shadow-2xl relative overflow-hidden ring-1 ring-cyan-500/20">
          <div className="absolute top-0 right-0 h-48 w-48 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="max-w-xl">
              <div className="flex items-center gap-2 mb-2">
                <span className="flex h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
                <span className="text-[11px] font-mono font-bold tracking-wider text-cyan-400 uppercase">
                  CENTRAL DAKOTA AI COPILOT
                </span>
                <span className="rounded-full bg-cyan-500/10 px-2 py-0.5 text-[9px] font-mono text-cyan-300 border border-cyan-500/20">
                  GROUNDED RAG
                </span>
              </div>
              <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
                Investigate Equities & Syndicates in Natural Language
              </h2>
              <p className="text-xs text-slate-300 mt-1.5 leading-relaxed">
                Ask questions across Dakota's 2,615+ stocks, real-time news feeds, syndicate campaigns, and 5-pillar risk outputs. Answers cite underlying evidence records with 0% fabricated claims.
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 shrink-0">
              <Link
                href="/intelligence"
                className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-600 to-indigo-600 px-5 py-3 text-xs font-bold text-white shadow-lg shadow-cyan-500/25 hover:opacity-95 transition-all"
              >
                <Sparkles className="h-4 w-4" />
                <span>Launch AI Copilot</span>
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-white/[0.08] flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-slate-400 font-mono">Suggested inquiries:</span>
            {[
              "Why did VARANIUM's risk score change?",
              "Summarize the most important news affecting my watchlist.",
              "Show evidence for CLOUD pump campaign.",
            ].map((sample, idx) => (
              <Link
                key={idx}
                href={`/intelligence`}
                className="rounded-md border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-slate-300 hover:border-cyan-500/40 hover:bg-cyan-500/10 hover:text-cyan-200 transition"
              >
                {sample}
              </Link>
            ))}
          </div>
        </section>

        {/* Forensic Ingestion Station */}
        <section className="rounded-2xl border border-white/[0.1] bg-[#0a0e17]/90 shadow-2xl backdrop-blur-xl p-6 sm:p-8 relative overflow-hidden">
          <div className="absolute top-0 right-0 h-40 w-40 bg-cyan-500/5 blur-3xl pointer-events-none" />
          
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
            <div>
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <span>Check Tip Authenticity</span>
                <span className="rounded bg-white/10 px-2 py-0.5 text-[10px] font-mono text-slate-300 font-normal">
                  INSTANT SCAN
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Paste any forwarded WhatsApp text, Telegram channel alert, or SMS stock recommendation.
              </p>
            </div>

            {/* Quick Demo Preset Buttons */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] text-slate-400 mr-1 hidden sm:inline">Try preset:</span>
              {SAMPLE_TIPS.map((sample) => (
                <button
                  key={sample.ticker}
                  type="button"
                  onClick={() => handlePresetClick(sample.text)}
                  className="rounded-lg border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-xs text-slate-300 hover:border-cyan-500/40 hover:bg-cyan-500/10 hover:text-cyan-300 transition"
                >
                  {sample.label}
                </button>
              ))}
            </div>
          </div>

          <div className="relative">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Example:&#10;URGENT BUY VARANIUM TARGET ₹500. Guaranteed 300% returns in 3 days. SEBI REG: INH000008912. Buy before upper circuit locks! VIP call."
              className="min-h-36 w-full resize-y rounded-xl border border-white/[0.08] bg-black/50 p-4 text-sm text-slate-100 placeholder:text-slate-600 outline-none transition focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/30 font-mono"
            />
            
            {text && (
              <div className="absolute bottom-3 right-3 text-[11px] font-mono text-slate-500">
                {text.length} characters
              </div>
            )}
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <Info className="w-3.5 h-3.5 text-slate-400" />
              <span>Dakota automatically cross-references exchange trading bands and promoter pledging.</span>
            </div>

            <div className="flex items-center gap-3">
              {text && (
                <button
                  type="button"
                  onClick={() => {
                    setText("");
                    setResult(null);
                    setError("");
                  }}
                  className="rounded-xl px-4 py-2.5 text-xs font-semibold text-slate-400 hover:text-white transition"
                >
                  Clear
                </button>
              )}

              <button
                type="button"
                onClick={() => analyzeTip()}
                disabled={loading || !text.trim()}
                className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-cyan-500/20 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition"
              >
                {loading ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    <span>Investigating Evidence...</span>
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4" />
                    <span>Screen Tip</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {error && (
            <div className="mt-5 rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-300 flex items-start gap-3">
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">Analysis Notice:</span> {error}
              </div>
            </div>
          )}
        </section>

        {/* Results Workspace */}
        {stock && (
          <section className="mt-8 rounded-2xl border border-white/[0.1] bg-[#0a0e17] shadow-2xl p-6 sm:p-8 space-y-8 animate-in fade-in duration-200">
            {/* Top Verdict Ribbon */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 border-b border-white/[0.08] pb-6">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-xs font-mono uppercase tracking-widest text-slate-400">
                    FORENSIC TARGET VERDICT
                  </span>
                  <span className={`text-[11px] px-2.5 py-0.5 rounded-full font-mono font-bold border ${
                    stock.band === "High"
                      ? "border-rose-500/40 bg-rose-500/15 text-rose-300"
                      : stock.band === "Elevated"
                      ? "border-amber-500/40 bg-amber-500/15 text-amber-300"
                      : "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                  }`}>
                    {stock.band.toUpperCase()} RISK TIER
                  </span>
                </div>

                <div className="flex items-center gap-3">
                  <h2 className="text-3xl sm:text-4xl font-black text-white">
                    {stock.ticker}
                  </h2>
                  <Link
                    href={`/stocks/${stock.ticker}`}
                    className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-cyan-300 hover:bg-cyan-500/10 transition"
                  >
                    <span>Full Stock Terminal</span>
                    <ExternalLink className="w-3 h-3" />
                  </Link>
                </div>

                {stock.as_of && (
                  <p className="text-xs text-slate-500 mt-1">
                    Evaluated against market snapshot as of {stock.as_of}
                  </p>
                )}
              </div>

              {/* Assessment Narrative */}
              <div className="max-w-md rounded-xl border border-white/[0.08] bg-white/[0.02] p-4 text-xs text-slate-300 leading-relaxed">
                <span className="font-semibold text-white block mb-1 text-sm">Forensic Summary:</span>
                {stock.verdict}
              </div>
            </div>

            {/* Interactive RiskRing & 5-Group Contribution Breakdown */}
            <div>
              <div className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-3">
                Score Decomposition (Click Ring to Expand Pillar Bar Breakdown)
              </div>
              <RiskRing
                score={stock.score}
                contributions={stock.contributions}
                contribution_labels={stock.contribution_labels}
                reasons={result.combined_reasons || stock.reasons}
                ticker={stock.ticker}
                defaultExpanded={true}
              />
            </div>

            {/* Extracted Tip Signals 4-Card Grid */}
            {parsed && (
              <div>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300 mb-3">
                  Extracted Tip Attributes
                </h3>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <div className="text-[10px] font-mono uppercase text-slate-500">Target Ticker</div>
                    <div className="text-lg font-bold text-white mt-1">
                      {parsed.tickers && parsed.tickers.length > 0 ? parsed.tickers.join(", ") : "None Detected"}
                    </div>
                  </div>

                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <div className="text-[10px] font-mono uppercase text-slate-500">Claimed Price Target</div>
                    <div className="text-lg font-bold text-cyan-300 mt-1">
                      {parsed.price_target != null ? `₹${parsed.price_target.toLocaleString("en-IN")}` : "Not Specified"}
                    </div>
                  </div>

                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <div className="text-[10px] font-mono uppercase text-slate-500">Scam Markers Detected</div>
                    <div className={`text-lg font-bold mt-1 ${
                      (parsed.n_scam_markers ?? 0) > 0 ? "text-rose-400" : "text-emerald-400"
                    }`}>
                      {parsed.n_scam_markers ?? 0} markers found
                    </div>
                  </div>

                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <div className="text-[10px] font-mono uppercase text-slate-500">SEBI Registration Status</div>
                    <div className="text-sm font-semibold text-slate-200 mt-1">
                      {parsed.sebi_reg_claimed
                        ? parsed.sebi_reg_number
                          ? `Claimed: ${parsed.sebi_reg_number}`
                          : "Claimed (Unverified)"
                        : "No Registration Claimed"}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Forensic Evidence Observations */}
            {result.combined_reasons && result.combined_reasons.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300 mb-3">
                  Verified Forensic Evidence
                </h3>
                <div className="space-y-2">
                  {result.combined_reasons.map((reason, idx) => (
                    <div
                      key={idx}
                      className="flex items-start gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 text-xs text-slate-300"
                    >
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cyan-500/10 text-[10px] font-mono text-cyan-400">
                        {idx + 1}
                      </span>
                      <span>{reason}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Market Observation Badges */}
            <MarketBadges
              observations={
                result.combined_reasons?.map((r: string) => ({
                  text: r,
                  severity:
                    r.toLowerCase().includes("volume") || r.toLowerCase().includes("rsi")
                      ? "high"
                      : "medium",
                  signal: "market_obs",
                })) || []
              }
            />

            {/* Interactive Stock Price Chart */}
            <div className="border-t border-white/[0.08] pt-6">
              <StockChart ticker={stock?.ticker} data={stock?.market?.chart || []} />
            </div>

            {/* Actionable Next Steps Checklist */}
            {result.next_steps && result.next_steps.length > 0 && (
              <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/[0.03] p-5">
                <h3 className="text-sm font-semibold text-cyan-300 flex items-center gap-2 mb-3">
                  <CheckCircle2 className="w-4 h-4 text-cyan-400" />
                  <span>Recommended Risk Mitigation Steps</span>
                </h3>
                <div className="space-y-2 text-xs text-slate-300">
                  {result.next_steps.map((step, idx) => (
                    <div key={idx} className="flex items-start gap-2">
                      <span className="font-mono text-cyan-400">{idx + 1}.</span>
                      <span>{step}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Institutional Disclaimer */}
            {result.disclaimer && (
              <p className="text-[11px] leading-relaxed text-slate-500 border-t border-white/[0.05] pt-4">
                {result.disclaimer}
              </p>
            )}
          </section>
        )}

        {/* Results Workspace: Non-Stock / Index / Unmatched Query State */}
        {result && !stock && (
          <section className="mt-8 rounded-2xl border border-white/[0.1] bg-[#0a0e17] shadow-2xl p-6 sm:p-8 space-y-6 animate-in fade-in duration-200">
            {/* Header Ribbon */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 border-b border-white/[0.08] pb-6">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-xs font-mono uppercase tracking-widest text-slate-400">
                    FORENSIC TIP INGESTION RESULT
                  </span>
                  <span className={`text-[11px] px-2.5 py-0.5 rounded-full font-mono font-bold border ${
                    parsed?.is_index
                      ? "border-cyan-500/40 bg-cyan-500/15 text-cyan-300"
                      : (parsed?.n_scam_markers ?? 0) > 0
                      ? "border-amber-500/40 bg-amber-500/15 text-amber-300"
                      : "border-slate-500/40 bg-slate-500/15 text-slate-300"
                  }`}>
                    {parsed?.is_index
                      ? "BENCHMARK INDEX ADVISORY"
                      : (parsed?.n_scam_markers ?? 0) > 0
                      ? "SUSPICIOUS PATTERNS DETECTED"
                      : "TELEMETRY SCAN COMPLETE"}
                  </span>
                </div>

                <div className="flex items-center gap-3">
                  <h2 className="text-2xl sm:text-3xl font-black text-white">
                    {result.headline || "Tip Analysis Completed"}
                  </h2>
                </div>

                <p className="text-xs text-slate-400 mt-2 max-w-xl">
                  {parsed?.is_index
                    ? `Input references '${parsed.index_name || "a benchmark index"}' (an aggregate index basket). Dakota's 5-pillar forensic engine monitors individual listed corporate equities.`
                    : "Tip text was parsed and cross-referenced against Dakota's universe and forensic pattern signatures."}
                </p>
              </div>

              {/* Scanned Fingerprint pill */}
              {parsed?.fingerprint && (
                <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-3 text-xs font-mono text-slate-400 flex flex-col gap-1 shrink-0">
                  <span className="text-[10px] text-slate-500 uppercase">Audit Fingerprint</span>
                  <span className="text-cyan-400 font-bold">{parsed.fingerprint}</span>
                </div>
              )}
            </div>

            {/* Extracted Tip Signals 4-Card Grid */}
            {parsed && (
              <div>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300 mb-3">
                  Extracted Tip Attributes
                </h3>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <div className="text-[10px] font-mono uppercase text-slate-500">Target Asset / Index</div>
                    <div className="text-base font-bold text-white mt-1">
                      {parsed.index_name || (parsed.tickers && parsed.tickers.length > 0 ? parsed.tickers.join(", ") : "No Equity Matched")}
                    </div>
                  </div>

                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <div className="text-[10px] font-mono uppercase text-slate-500">Claimed Price Target</div>
                    <div className="text-base font-bold text-cyan-300 mt-1">
                      {parsed.price_target != null ? `₹${parsed.price_target.toLocaleString("en-IN")}` : "None Specified"}
                    </div>
                  </div>

                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <div className="text-[10px] font-mono uppercase text-slate-500">Scam Markers</div>
                    <div className={`text-base font-bold mt-1 ${
                      (parsed.n_scam_markers ?? 0) > 0 ? "text-rose-400" : "text-emerald-400"
                    }`}>
                      {parsed.n_scam_markers ?? 0} markers detected
                    </div>
                  </div>

                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <div className="text-[10px] font-mono uppercase text-slate-500">SEBI Registration Status</div>
                    <div className="text-sm font-semibold text-slate-200 mt-1">
                      {parsed.sebi_reg_claimed
                        ? parsed.sebi_reg_number
                          ? `Claimed: ${parsed.sebi_reg_number}`
                          : "Claimed (Unverified)"
                        : "No Registration Claimed"}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Actionable Guidance & Next Steps */}
            {result.next_steps && result.next_steps.length > 0 && (
              <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/[0.03] p-5">
                <h3 className="text-sm font-semibold text-cyan-300 flex items-center gap-2 mb-3">
                  <CheckCircle2 className="w-4 h-4 text-cyan-400" />
                  <span>Guidance & Recommended Next Steps</span>
                </h3>
                <div className="space-y-2 text-xs text-slate-300">
                  {result.next_steps.map((step, idx) => (
                    <div key={idx} className="flex items-start gap-2">
                      <span className="font-mono text-cyan-400 font-bold">{idx + 1}.</span>
                      <span>{step}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Quick Test Suggested Stocks */}
            <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-5">
              <div className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-3">
                Quick Test Verified Equities & Constituents
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {[
                  { label: "HDFCBANK (Top Nifty Weight)", text: "BUY HDFCBANK TARGET 1800" },
                  { label: "RELIANCE (Nifty Heavyweight)", text: "BUY RELIANCE TARGET 3200" },
                  { label: "VARANIUM (Pump Scam Sample)", text: "URGENT BUY VARANIUM TARGET ₹500. Guaranteed 300% returns in 3 days. SEBI REG: INH000008912. Buy before upper circuit locks! VIP call." },
                  { label: "ZOMATO (Cartel Pattern)", text: "SURE SHOT BUY ZOMATO CMP 265 TARGET 350. Heavy insider operator buying confirmed by cartel syndicate. 100% jackpot call today." },
                ].map((item, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handlePresetClick(item.text)}
                    className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-200 hover:border-cyan-500/40 hover:bg-cyan-500/10 hover:text-cyan-200 transition"
                  >
                    🔍 {item.label}
                  </button>
                ))}
                <Link
                  href="/stocks"
                  className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-300 hover:bg-cyan-500/20 transition flex items-center gap-1"
                >
                  <span>Explore 2,600+ Stocks Screener</span>
                  <ExternalLink className="h-3 w-3" />
                </Link>
              </div>
            </div>

            {/* Institutional Disclaimer */}
            {result.disclaimer && (
              <p className="text-[11px] leading-relaxed text-slate-500 border-t border-white/[0.05] pt-4">
                {result.disclaimer}
              </p>
            )}
          </section>
        )}
      </div>

      <footer className="border-t border-white/[0.08] bg-[#070b12] py-6 text-center text-xs text-slate-500 font-mono">
        DAKOTA FINANCIAL INTELLIGENCE PLATFORM • NOT INVESTMENT ADVICE • EVIDENCE-BASED FORENSIC SURVEILLANCE
      </footer>
    </main>
  );
}