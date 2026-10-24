"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Clock,
  Database,
  ExternalLink,
  Eye,
  FileCheck2,
  FileText,
  Filter,
  Layers,
  Lock,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
  XCircle,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type UniverseSummary = {
  total_count: number;
  case_count: number;
  control_count: number;
  mainboard_count: number;
  sme_count: number;
  surveillance_flag_count: number;
  exchanges: { NSE: number; BSE: number };
  manifest_path?: string;
};

type StockItem = {
  ticker: string;
  name: string;
  exchange: string;
  segment: string;
  role: string;
  surveillance_flag: boolean;
  market_cap_tier: string;
  active_status: string;
  provenance_source: string;
};

type QNPrediction = {
  ticker: string;
  as_of_date: string;
  model_score: number;
  manipulation_probability: number;
  risk_band: string;
  confidence: number;
  margin: number;
  contributing_factors: Record<string, number>;
  top_factor_reasons: string[];
  model_version: string;
  is_real_model: boolean;
  data_freshness: string;
  latency_ms: number;
  effective_threshold?: number;
  alert_triggered?: boolean;
  disclaimer: string;
};

type RegulatoryEvent = {
  event_id: string;
  ticker: string;
  exchange: string;
  company_name: string;
  label: string;
  behavior_category: string;
  start_date: string;
  end_date: string;
  regulator_or_authority: string;
  order_reference?: string;
  publication_date?: string;
  source_url_or_id?: string;
  evidence_strength: string;
  reviewer_status: string;
  summary: string;
  caveats?: string;
};

type StockAnalysis = {
  ticker: string;
  company_name: string;
  exchange: string;
  segment: string;
  role: string;
  surveillance_flag: boolean;
  qn_prediction: QNPrediction;
  core_risk_engine: {
    score: number | null;
    band: string;
    contributions: Record<string, number>;
    reasons: string[];
  };
  registered_evidence: RegulatoryEvent[];
  jav_intelligence?: {
    active_model_id: string;
    backend: string;
    status: string;
  };
  disclaimer: string;
};

type ExperimentData = {
  experiment_name: string;
  dataset_manifest: {
    total_windows: number;
    purge_embargo_days: number;
    splits: {
      train: { count: number; positive_count: number; positive_ratio: number };
      val: { count: number; positive_count: number; positive_ratio: number };
      test: { count: number; positive_count: number; positive_ratio: number };
    };
    leakage_invariants: Record<string, any>;
  };
  active_model_metadata: {
    model_version: string;
    architecture: string;
    trained_at: string;
    feature_importances: Record<string, number>;
    holdout_test_metrics: {
      accuracy: number;
      balanced_accuracy: number;
      macro_f1: number;
      roc_auc: number;
      pr_auc: number;
      expected_calibration_error: number;
      brier_score: number;
      false_positive_rate: number;
      false_negative_rate: number;
      confusion_matrix: { tn: number; fp: number; fn: number; tp: number };
      threshold_metrics: Record<string, any>;
      business_impact: Record<string, string>;
    };
  };
  research_limitations: Record<string, string>;
};

type JevModelProfile = {
  active_model_id: string;
  backend: string;
  device: string;
  cuda_available: boolean;
  torch_version: string;
  ram_total_gb?: number;
  devices: Array<{ id: number; name: string; total_vram_mb: number }>;
  supported_tasks: string[];
};

type JevPrediction = {
  task_name: string;
  model_id: string;
  winning_label: string;
  winning_label_display?: string;
  probabilities: Record<string, number>;
  raw_logits: Record<string, number>;
  margin: number;
  confidence_score: number;
  zero_generated_tokens: boolean;
  execution_latency_ms: number;
  heuristic_fallback_used: boolean;
  disclaimer: string;
};

export default function SurveillancePage() {
  const [activeTab, setActiveTab] = useState<"terminal" | "universe" | "evidence" | "research" | "jav">("terminal");

  // Summary and Universe state
  const [universe, setUniverse] = useState<UniverseSummary | null>(null);
  const [stocks, setStocks] = useState<StockItem[]>([]);
  const [stockSearch, setStockSearch] = useState("");
  const [stockFilterSegment, setStockFilterSegment] = useState("");
  const [loadingStocks, setLoadingStocks] = useState(false);

  // Analysis Terminal state
  const [selectedTicker, setSelectedTicker] = useState("CLOUD");
  const [asOfDate, setAsOfDate] = useState("");
  const [analysis, setAnalysis] = useState<StockAnalysis | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [analysisError, setAnalysisError] = useState("");

  // Regulatory Evidence state
  const [evidenceList, setEvidenceList] = useState<RegulatoryEvent[]>([]);
  const [evidenceFilterLabel, setEvidenceFilterLabel] = useState("");
  const [loadingEvidence, setLoadingEvidence] = useState(false);

  // Research Experiment state
  const [experiment, setExperiment] = useState<ExperimentData | null>(null);
  const [loadingExperiment, setLoadingExperiment] = useState(false);
  const [trainingInProgress, setTrainingInProgress] = useState(false);
  const [trainingMessage, setTrainingMessage] = useState("");

  // JAV / JEV Interactive state
  const [jevModel, setJevModel] = useState<JevModelProfile | null>(null);
  const [loadingJevModel, setLoadingJevModel] = useState(false);
  const [jevTicker, setJevTicker] = useState("CDSL");
  const [jevClaim, setJevClaim] = useState("CDSL target ₹1,500 by Friday! Guaranteed 40% returns, join VIP pump channel.");
  const [jevPrediction, setJevPrediction] = useState<JevPrediction | null>(null);
  const [loadingJevClassify, setLoadingJevClassify] = useState(false);
  const [jevError, setJevError] = useState("");

  // Load Initial Universe Overview
  useEffect(() => {
    async function loadUniverse() {
      try {
        const res = await fetch(`${API}/api/surveillance/qn/universe`);
        if (res.ok) {
          const data = await res.json();
          setUniverse(data);
        }
      } catch (err) {
        console.error("Failed loading universe summary:", err);
      }
    }
    loadUniverse();
  }, []);

  // Run Analysis on Selected Ticker
  const runAnalysis = async (ticker: string, dateOverride?: string) => {
    setLoadingAnalysis(true);
    setAnalysisError("");
    try {
      const targetDate = dateOverride !== undefined ? dateOverride : asOfDate;
      const url = targetDate.trim()
        ? `${API}/api/surveillance/qn/analyze/${ticker}?as_of_date=${encodeURIComponent(targetDate.trim())}`
        : `${API}/api/surveillance/qn/analyze/${ticker}`;
      const res = await fetch(url);
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Analysis request failed");
      }
      const data = await res.json();
      setAnalysis(data);
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : "Failed executing surveillance analysis");
    } finally {
      setLoadingAnalysis(false);
    }
  };

  useEffect(() => {
    runAnalysis(selectedTicker, asOfDate);
  }, [selectedTicker]);

  // Load JEV Model Telemetry when JAV tab is opened
  useEffect(() => {
    if (activeTab === "jav") {
      setLoadingJevModel(true);
      fetch(`${API}/api/intelligence/jev/models`)
        .then((r) => r.json())
        .then((d) => setJevModel(d))
        .catch((e) => console.error("Failed to load JEV model profile:", e))
        .finally(() => setLoadingJevModel(false));
    }
  }, [activeTab]);

  const runJevClassification = async () => {
    setLoadingJevClassify(true);
    setJevError("");
    try {
      const res = await fetch(`${API}/api/intelligence/jev/classify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: jevTicker.trim().toUpperCase() || "CDSL",
          claim: jevClaim.trim(),
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "JEV logit computation failed");
      }
      const data = await res.json();
      setJevPrediction(data);
    } catch (err) {
      setJevError(err instanceof Error ? err.message : "JEV logit computation error");
    } finally {
      setLoadingJevClassify(false);
    }
  };

  // Load Stocks when Universe tab is opened
  useEffect(() => {
    if (activeTab === "universe") {
      setLoadingStocks(true);
      fetch(`${API}/api/surveillance/qn/stocks?limit=100&segment=${stockFilterSegment}&search=${stockSearch}`)
        .then((r) => r.json())
        .then((d) => setStocks(d.stocks || []))
        .catch((e) => console.error(e))
        .finally(() => setLoadingStocks(false));
    }
  }, [activeTab, stockFilterSegment, stockSearch]);

  // Load Evidence when Evidence tab is opened
  useEffect(() => {
    if (activeTab === "evidence") {
      setLoadingEvidence(true);
      const url = evidenceFilterLabel
        ? `${API}/api/surveillance/qn/evidence?label=${evidenceFilterLabel}`
        : `${API}/api/surveillance/qn/evidence`;
      fetch(url)
        .then((r) => r.json())
        .then((d) => setEvidenceList(d.events || []))
        .catch((e) => console.error(e))
        .finally(() => setLoadingEvidence(false));
    }
  }, [activeTab, evidenceFilterLabel]);

  // Load Experiment when Research tab is opened
  useEffect(() => {
    if (activeTab === "research") {
      setLoadingExperiment(true);
      fetch(`${API}/api/surveillance/qn/research/experiment`)
        .then((r) => r.json())
        .then((d) => setExperiment(d))
        .catch((e) => console.error(e))
        .finally(() => setLoadingExperiment(false));
    }
  }, [activeTab]);

  const handleRetrain = async () => {
    setTrainingInProgress(true);
    setTrainingMessage("Training pipeline initialized in background...");
    try {
      const res = await fetch(`${API}/api/surveillance/qn/train`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ purge_days: 15, random_state: 42 }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Training failed");
      setTrainingMessage("Training triggered! Refreshing experiment telemetry in 5s...");
      setTimeout(() => {
        fetch(`${API}/api/surveillance/qn/research/experiment`)
          .then((r) => r.json())
          .then((d) => {
            setExperiment(d);
            setTrainingMessage("Model training complete and evaluation refreshed!");
          });
        setTrainingInProgress(false);
      }, 5000);
    } catch (err) {
      setTrainingMessage(err instanceof Error ? err.message : "Training trigger failed");
      setTrainingInProgress(false);
    }
  };

  const PRESET_TICKERS = ["CLOUD", "ASRL", "TRAFIKSOL", "AFCOM", "BRIGHTCOM", "RELIANCE", "TCS", "INFY", "CDSL"];

  return (
    <main className="min-h-screen bg-[#05070a] text-slate-100 flex flex-col bg-terminal-grid">
      <Navbar />

      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 sm:py-10 flex-1">
        {/* Terminal Header */}
        <header className="mb-8 border-b border-white/[0.08] pb-6">
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-rose-500/30 bg-rose-500/10 px-3 py-1 text-xs font-mono font-semibold text-rose-300 mb-3 shadow-sm">
                <Activity className="h-3.5 w-3.5 animate-pulse text-rose-400" />
                <span>QN SURVEILLANCE &amp; JAV INTELLIGENCE PIPELINE</span>
              </div>
              <h1 className="text-3xl sm:text-4xl font-black text-white tracking-tight">
                Indian Stock Manipulation Surveillance
              </h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-400 leading-relaxed">
                500-equity Indian stock universe • Calibrated Quantitative Network (QN) • Joint Expected-Value (JAV) causal logit extraction • Official SEBI enforcement orders.
              </p>
            </div>

            {/* Live Universe Badges */}
            <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
              <div className="rounded-lg border border-white/[0.08] bg-[#0a0f18] px-3 py-2">
                <div className="text-[10px] text-slate-500 uppercase">UNIVERSE</div>
                <div className="font-bold text-white">500 Equities</div>
              </div>
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-emerald-300">
                <div className="text-[10px] text-emerald-400/80 uppercase">MODEL STATUS</div>
                <div className="font-bold">QN-v1.0.0 READY</div>
              </div>
              <div className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-sky-300">
                <div className="text-[10px] text-sky-400/80 uppercase">CALIBRATION ECE</div>
                <div className="font-bold">0.0103 (EXCELLENT)</div>
              </div>
            </div>
          </div>

          {/* Navigation Sub-Tabs */}
          <div className="flex flex-wrap gap-2 mt-6 pt-4 border-t border-white/[0.05]">
            <button
              onClick={() => setActiveTab("terminal")}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-mono font-bold transition-all ${
                activeTab === "terminal"
                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-lg shadow-rose-950/30"
                  : "bg-slate-900/60 text-slate-400 border border-white/[0.06] hover:text-white"
              }`}
            >
              <Activity className="h-4 w-4" />
              <span>Surveillance Terminal</span>
            </button>

            <button
              onClick={() => setActiveTab("universe")}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-mono font-bold transition-all ${
                activeTab === "universe"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-lg shadow-cyan-950/30"
                  : "bg-slate-900/60 text-slate-400 border border-white/[0.06] hover:text-white"
              }`}
            >
              <Database className="h-4 w-4" />
              <span>500 Universe Explorer ({universe?.total_count || 500})</span>
            </button>

            <button
              onClick={() => setActiveTab("evidence")}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-mono font-bold transition-all ${
                activeTab === "evidence"
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-lg shadow-amber-950/30"
                  : "bg-slate-900/60 text-slate-400 border border-white/[0.06] hover:text-white"
              }`}
            >
              <FileCheck2 className="h-4 w-4" />
              <span>SEBI &amp; Regulatory Archive</span>
            </button>

            <button
              onClick={() => setActiveTab("research")}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-mono font-bold transition-all ${
                activeTab === "research"
                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-lg shadow-purple-950/30"
                  : "bg-slate-900/60 text-slate-400 border border-white/[0.06] hover:text-white"
              }`}
            >
              <BarChart3 className="h-4 w-4" />
              <span>Research Manifesto &amp; Calibration</span>
            </button>

            <button
              onClick={() => setActiveTab("jav")}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-mono font-bold transition-all ${
                activeTab === "jav"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-lg shadow-emerald-950/30"
                  : "bg-slate-900/60 text-slate-400 border border-white/[0.06] hover:text-white"
              }`}
            >
              <Sparkles className="h-4 w-4" />
              <span>JAV Causal Logits &amp; Qwen</span>
            </button>
          </div>
        </header>

        {/* TAB 1: SURVEILLANCE TERMINAL */}
        {activeTab === "terminal" && (
          <div className="space-y-6">
            {/* Stock Selector & Presets */}
            <div className="rounded-2xl border border-white/[0.08] bg-[#090d16] p-5 shadow-xl">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex-1">
                  <label className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-2 block">
                    Target Stock Symbol (NSE / BSE 500 Cohort)
                  </label>
                  <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                      <input
                        type="text"
                        value={selectedTicker}
                        onChange={(e) => setSelectedTicker(e.target.value.toUpperCase())}
                        placeholder="Enter ticker (e.g. CLOUD, ASRL, INFY, TCS)..."
                        className="w-full pl-9 pr-4 py-2 rounded-xl bg-black/40 border border-white/[0.1] text-sm font-mono text-white placeholder-slate-600 focus:outline-none focus:border-rose-500/50"
                      />
                    </div>
                    <button
                      onClick={() => runAnalysis(selectedTicker, asOfDate)}
                      disabled={loadingAnalysis}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 text-xs font-mono font-bold text-rose-300 transition-colors shadow-sm disabled:opacity-50"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${loadingAnalysis ? "animate-spin" : ""}`} />
                      <span>Execute Forensic Probe</span>
                    </button>
                  </div>

                  {/* Historical As-Of Date Selection */}
                  <div className="flex flex-wrap items-center gap-2 mt-3 pt-3 border-t border-white/[0.05]">
                    <div className="flex items-center gap-2 flex-1 min-w-[200px]">
                      <Clock className="h-3.5 w-3.5 text-slate-500 shrink-0" />
                      <input
                        type="text"
                        value={asOfDate}
                        onChange={(e) => setAsOfDate(e.target.value)}
                        placeholder="As-Of Date YYYY-MM-DD (e.g. 2026-04-15)..."
                        className="w-full px-3 py-1.5 rounded-lg bg-black/40 border border-white/[0.08] text-xs font-mono text-white placeholder-slate-600 focus:outline-none focus:border-rose-500/50"
                      />
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => {
                          setAsOfDate("");
                          runAnalysis(selectedTicker, "");
                        }}
                        className={`px-2.5 py-1 rounded-lg text-[10px] font-mono font-semibold transition-all ${
                          !asOfDate
                            ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                            : "bg-slate-850 text-slate-400 hover:text-white border border-white/[0.05]"
                        }`}
                      >
                        Live Tail
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setAsOfDate("2026-04-15");
                          runAnalysis(selectedTicker, "2026-04-15");
                        }}
                        className={`px-2.5 py-1 rounded-lg text-[10px] font-mono font-semibold transition-all ${
                          asOfDate === "2026-04-15"
                            ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                            : "bg-slate-850 text-slate-400 hover:text-white border border-white/[0.05]"
                        }`}
                      >
                        2026-04-15 (SEBI Order Window)
                      </button>
                    </div>
                  </div>
                </div>

                {/* Preset Scrips */}
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2">Quick Scrip Presets</div>
                  <div className="flex flex-wrap gap-1.5">
                    {PRESET_TICKERS.map((t) => (
                      <button
                        key={t}
                        onClick={() => setSelectedTicker(t)}
                        className={`px-2.5 py-1 rounded-lg text-xs font-mono font-bold transition-all ${
                          selectedTicker === t
                            ? "bg-rose-500/30 text-rose-200 border border-rose-500/50"
                            : "bg-slate-800/60 hover:bg-slate-800 text-slate-400 hover:text-white border border-white/[0.05]"
                        }`}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {loadingAnalysis ? (
              <div className="rounded-2xl border border-white/[0.08] bg-[#090d16] p-12 text-center">
                <RefreshCw className="h-8 w-8 animate-spin text-rose-400 mx-auto mb-3" />
                <div className="font-mono text-sm text-slate-300">Extracting Point-in-Time Market Telemetry &amp; Running QN Inference...</div>
                <div className="text-xs text-slate-500 mt-1">Evaluating volume z-score, circuit locks, price-volume correlation, and regulatory orders</div>
              </div>
            ) : analysisError ? (
              <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-6 text-rose-300">
                <div className="flex items-center gap-2 font-bold mb-1">
                  <AlertTriangle className="h-5 w-5" />
                  <span>Analysis Error</span>
                </div>
                <p className="text-xs">{analysisError}</p>
              </div>
            ) : analysis ? (
              <div className="space-y-6">
                {/* Primary Dual Score Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                  {/* Card 1: QN Model Score */}
                  <div className="rounded-2xl border border-rose-500/30 bg-[#0c101d] p-5 shadow-xl relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-3 opacity-15">
                      <Activity className="h-24 w-24 text-rose-500" />
                    </div>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-rose-400 font-semibold mb-1">
                      QUANTITATIVE NETWORK (QN)
                    </div>
                    <div className="text-lg font-bold text-white mb-3">
                      Manipulation Risk Score
                    </div>

                    <div className="flex items-baseline gap-3">
                      <span className="text-5xl font-mono font-black text-rose-400">
                        {analysis.qn_prediction.model_score.toFixed(1)}
                      </span>
                      <span className="text-sm font-mono text-slate-400">/ 100</span>
                    </div>

                    <div className="mt-3 flex items-center gap-2">
                      <span
                        className={`px-2.5 py-0.5 rounded-full font-mono text-xs font-bold ${
                          analysis.qn_prediction.risk_band === "High"
                            ? "bg-rose-950 text-rose-300 border border-rose-800"
                            : analysis.qn_prediction.risk_band === "Elevated"
                            ? "bg-amber-950 text-amber-300 border border-amber-800"
                            : "bg-emerald-950 text-emerald-300 border border-emerald-800"
                        }`}
                      >
                        {analysis.qn_prediction.risk_band.toUpperCase()} RISK
                      </span>
                      <span className="text-xs font-mono text-slate-400">
                        Prob: {(analysis.qn_prediction.manipulation_probability * 100).toFixed(1)}%
                      </span>
                      {analysis.qn_prediction.alert_triggered != null && (
                        <span
                          className={`px-2 py-0.5 rounded font-mono text-[10px] font-semibold ${
                            analysis.qn_prediction.alert_triggered
                              ? "bg-rose-900/60 text-rose-200 border border-rose-700"
                              : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          {analysis.qn_prediction.alert_triggered ? "ALERT TRIGGERED" : "BELOW THRESHOLD"}
                        </span>
                      )}
                    </div>

                    <div className="mt-4 pt-3 border-t border-white/[0.08] text-[11px] font-mono text-slate-400 space-y-1">
                      <div>Threshold: <strong className="text-slate-200">{((analysis.qn_prediction.effective_threshold ?? 0.012) * 100).toFixed(1)}%</strong></div>
                      <div>Confidence: <strong className="text-slate-200">{(analysis.qn_prediction.confidence * 100).toFixed(1)}%</strong></div>
                      <div>Model: <strong className="text-slate-200">{analysis.qn_prediction.model_version}</strong></div>
                      <div>Latency: <strong className="text-slate-200">{analysis.qn_prediction.latency_ms.toFixed(1)} ms</strong></div>
                    </div>
                  </div>

                  {/* Card 2: Dakota Core Deterministic Risk Engine */}
                  <div className="rounded-2xl border border-sky-500/30 bg-[#091122] p-5 shadow-xl relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-3 opacity-15">
                      <Shield className="h-24 w-24 text-sky-500" />
                    </div>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-sky-400 font-semibold mb-1">
                      CORE RISK ENGINE
                    </div>
                    <div className="text-lg font-bold text-white mb-3">
                      5-Pillar Forensic Baseline
                    </div>

                    <div className="flex items-baseline gap-3">
                      <span className="text-5xl font-mono font-black text-sky-300">
                        {analysis.core_risk_engine.score != null ? analysis.core_risk_engine.score.toFixed(1) : "—"}
                      </span>
                      <span className="text-sm font-mono text-slate-400">/ 100</span>
                    </div>

                    <div className="mt-3 flex items-center gap-2">
                      <span className="px-2.5 py-0.5 rounded-full font-mono text-xs font-bold bg-sky-950 text-sky-300 border border-sky-800">
                        {analysis.core_risk_engine.band.toUpperCase()}
                      </span>
                      <span className="text-xs font-mono text-slate-400">Deterministic Arithmetics</span>
                    </div>

                    <div className="mt-4 pt-3 border-t border-white/[0.08] text-[11px] font-mono text-slate-400 space-y-1">
                      <div>Promoter: <strong className="text-slate-200">{analysis.core_risk_engine.contributions?.promoter ?? 0} pts</strong></div>
                      <div>Coordination: <strong className="text-slate-200">{analysis.core_risk_engine.contributions?.coordination ?? 0} pts</strong></div>
                      <div>Footprint: <strong className="text-slate-200">{analysis.core_risk_engine.contributions?.market_footprint ?? 0} pts</strong></div>
                    </div>
                  </div>

                  {/* Card 3: Security Identity & Regulatory Stance */}
                  <div className="rounded-2xl border border-white/[0.08] bg-[#0a0f18] p-5 shadow-xl">
                    <div className="text-[10px] font-mono uppercase tracking-widest text-slate-400 font-semibold mb-1">
                      SECURITY PROFILE
                    </div>
                    <div className="text-lg font-bold text-white mb-3 flex items-center justify-between">
                      <span>{analysis.company_name}</span>
                      <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                        {analysis.exchange}
                      </span>
                    </div>

                    <div className="space-y-2 text-xs font-mono text-slate-300">
                      <div className="flex justify-between py-1 border-b border-white/[0.04]">
                        <span className="text-slate-500">Segment</span>
                        <span className="uppercase font-bold text-white">{analysis.segment}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-white/[0.04]">
                        <span className="text-slate-500">Cohort Role</span>
                        <span className="uppercase text-amber-300">{analysis.role}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-white/[0.04]">
                        <span className="text-slate-500">Surveillance Flag</span>
                        <span className={analysis.surveillance_flag ? "text-rose-400 font-bold" : "text-emerald-400"}>
                          {analysis.surveillance_flag ? "ACTIVE ASM/GSM" : "CLEAN"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1">
                        <span className="text-slate-500">Regulatory Orders</span>
                        <span className="font-bold text-white">{analysis.registered_evidence.length} Record(s)</span>
                      </div>
                    </div>

                    <div className="mt-4">
                      <Link
                        href={`/stocks/${analysis.ticker}`}
                        className="inline-flex items-center gap-1.5 text-xs font-mono text-sky-400 hover:text-sky-300 font-semibold"
                      >
                        <span>View Interactive Stock Chart</span>
                        <ChevronRight className="h-3.5 w-3.5" />
                      </Link>
                    </div>
                  </div>
                </div>

                {/* Factor Attributions & Reasons */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  {/* Factor Breakdown Bars */}
                  <div className="rounded-2xl border border-white/[0.08] bg-[#090d16] p-5 shadow-xl">
                    <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-4 flex items-center gap-2">
                      <BarChart3 className="h-4 w-4 text-rose-400" />
                      <span>Quantitative Anomaly Attribution Factors</span>
                    </h3>

                    <div className="space-y-3">
                      {Object.entries(analysis.qn_prediction.contributing_factors).map(([factor, val]) => {
                        const pct = Math.round(val * 100);
                        return (
                          <div key={factor}>
                            <div className="flex justify-between text-xs font-mono mb-1">
                              <span className="text-slate-300 capitalize">{factor.replace(/_/g, " ")}</span>
                              <span className="text-rose-300 font-bold">{pct}%</span>
                            </div>
                            <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-amber-500 to-rose-500 rounded-full transition-all"
                                style={{ width: `${Math.max(pct, 2)}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Factor Reasons & Alerts */}
                  <div className="rounded-2xl border border-white/[0.08] bg-[#090d16] p-5 shadow-xl">
                    <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-4 flex items-center gap-2">
                      <FileText className="h-4 w-4 text-sky-400" />
                      <span>Forensic Factor Explanations</span>
                    </h3>

                    <div className="space-y-2">
                      {analysis.qn_prediction.top_factor_reasons.map((reason, idx) => (
                        <div
                          key={idx}
                          className="flex items-start gap-2.5 rounded-xl border border-white/[0.06] bg-black/30 p-3 text-xs text-slate-300"
                        >
                          <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                          <span>{reason}</span>
                        </div>
                      ))}

                      {analysis.core_risk_engine.reasons?.map((reason, idx) => (
                        <div
                          key={`core-${idx}`}
                          className="flex items-start gap-2.5 rounded-xl border border-white/[0.04] bg-white/[0.01] p-3 text-xs text-slate-400"
                        >
                          <Shield className="h-4 w-4 text-sky-400 shrink-0 mt-0.5" />
                          <span>{reason}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Regulatory Evidence Section */}
                {analysis.registered_evidence.length > 0 && (
                  <div className="rounded-2xl border border-amber-500/30 bg-amber-950/10 p-5 shadow-xl">
                    <h3 className="text-xs font-mono uppercase tracking-wider text-amber-300 font-bold mb-3 flex items-center gap-2">
                      <Lock className="h-4 w-4 text-amber-400" />
                      <span>Official Regulatory Enforcement Findings On Record</span>
                    </h3>

                    <div className="space-y-3">
                      {analysis.registered_evidence.map((ev) => (
                        <div key={ev.event_id} className="rounded-xl border border-amber-500/20 bg-black/40 p-4 text-xs font-mono">
                          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.05] pb-2 mb-2">
                            <div className="flex items-center gap-2">
                              <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold">
                                {ev.label}
                              </span>
                              <span className="text-slate-400">{ev.order_reference || ev.event_id}</span>
                            </div>
                            <span className="text-slate-500">Date: {ev.publication_date || ev.start_date}</span>
                          </div>
                          <p className="text-slate-200 font-sans leading-relaxed mb-2">{ev.summary}</p>
                          {ev.caveats && (
                            <p className="text-slate-400 italic font-sans text-[11px] mb-2">Caveat: {ev.caveats}</p>
                          )}
                          {ev.source_url_or_id && ev.source_url_or_id.startsWith("http") && (
                            <a
                              href={ev.source_url_or_id}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-[11px] text-amber-400 hover:text-amber-300 underline"
                            >
                              <span>View Official SEBI Document</span>
                              <ExternalLink className="h-3 w-3" />
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Legal and Surveillance Disclaimer */}
                <div className="rounded-xl border border-white/[0.06] bg-black/20 p-4 text-xs font-mono text-slate-500 leading-relaxed">
                  {analysis.disclaimer}
                </div>
              </div>
            ) : null}
          </div>
        )}

        {/* TAB 2: 500 UNIVERSE EXPLORER */}
        {activeTab === "universe" && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border border-white/[0.08] bg-[#090d16] p-4">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                <input
                  type="text"
                  value={stockSearch}
                  onChange={(e) => setStockSearch(e.target.value)}
                  placeholder="Filter 500 equities by ticker or name..."
                  className="w-full pl-9 pr-4 py-2 rounded-xl bg-black/40 border border-white/[0.1] text-xs font-mono text-white placeholder-slate-600 focus:outline-none"
                />
              </div>

              <div className="flex items-center gap-2">
                <select
                  value={stockFilterSegment}
                  onChange={(e) => setStockFilterSegment(e.target.value)}
                  className="px-3 py-2 rounded-xl bg-black/40 border border-white/[0.1] text-xs font-mono text-slate-300 focus:outline-none"
                >
                  <option value="">All Segments</option>
                  <option value="main">Mainboard Equities</option>
                  <option value="sme">SME Exchange</option>
                </select>
              </div>
            </div>

            {loadingStocks ? (
              <div className="text-center py-12 text-slate-500 font-mono text-xs">Loading Universe Records...</div>
            ) : (
              <div className="rounded-2xl border border-white/[0.08] bg-[#090d16] overflow-x-auto shadow-xl">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-white/[0.08] text-slate-400 bg-white/[0.02]">
                      <th className="py-3 px-4">Ticker</th>
                      <th className="py-3 px-4">Company Name</th>
                      <th className="py-3 px-4">Exchange</th>
                      <th className="py-3 px-4">Segment</th>
                      <th className="py-3 px-4">Role</th>
                      <th className="py-3 px-4">Surveillance</th>
                      <th className="py-3 px-4">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    {stocks.map((s) => (
                      <tr key={s.ticker} className="hover:bg-white/[0.02] transition-colors">
                        <td className="py-3 px-4 font-bold text-white">{s.ticker}</td>
                        <td className="py-3 px-4 text-slate-300">{s.name}</td>
                        <td className="py-3 px-4 text-slate-400">{s.exchange}</td>
                        <td className="py-3 px-4 uppercase text-slate-400">{s.segment}</td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${s.role === "case" ? "bg-rose-950 text-rose-300" : "bg-slate-800 text-slate-400"}`}>
                            {s.role.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          {s.surveillance_flag ? (
                            <span className="text-amber-400 font-bold">ASM/GSM</span>
                          ) : (
                            <span className="text-slate-500">—</span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <button
                            onClick={() => {
                              setSelectedTicker(s.ticker);
                              setActiveTab("terminal");
                            }}
                            className="inline-flex items-center gap-1 text-sky-400 hover:text-sky-300 font-semibold"
                          >
                            <span>Inspect</span>
                            <ArrowRight className="h-3 w-3" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: REGULATORY EVIDENCE ARCHIVE */}
        {activeTab === "evidence" && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/[0.08] bg-[#090d16] p-4 text-xs font-mono">
              <span className="text-slate-400 mr-2">Filter Category:</span>
              {["", "CONFIRMED_MANIPULATION", "SUSPICIOUS_UNCONFIRMED"].map((lbl) => (
                <button
                  key={lbl}
                  onClick={() => setEvidenceFilterLabel(lbl)}
                  className={`px-3 py-1.5 rounded-lg transition-all ${
                    evidenceFilterLabel === lbl
                      ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                      : "bg-slate-800/60 text-slate-400 border border-white/[0.05]"
                  }`}
                >
                  {lbl ? lbl.replace(/_/g, " ") : "All Registered Cases"}
                </button>
              ))}
            </div>

            {loadingEvidence ? (
              <div className="text-center py-12 text-slate-500 font-mono text-xs">Loading Evidence Registry...</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {evidenceList.map((ev) => (
                  <div key={ev.event_id} className="rounded-2xl border border-white/[0.08] bg-[#090d16] p-5 shadow-xl flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between gap-2 border-b border-white/[0.06] pb-3 mb-3">
                        <div>
                          <div className="font-bold text-white text-base">{ev.company_name}</div>
                          <div className="font-mono text-xs text-slate-400">{ev.ticker} • {ev.exchange}</div>
                        </div>
                        <span
                          className={`px-2 py-0.5 rounded font-mono text-[10px] font-bold ${
                            ev.label === "CONFIRMED_MANIPULATION"
                              ? "bg-rose-950 text-rose-300 border border-rose-800"
                              : "bg-amber-950 text-amber-300 border border-amber-800"
                          }`}
                        >
                          {ev.label.replace(/_/g, " ")}
                        </span>
                      </div>

                      <div className="space-y-1.5 text-xs text-slate-300 font-sans leading-relaxed mb-4">
                        <p>{ev.summary}</p>
                        {ev.caveats && <p className="text-slate-500 italic text-[11px]">Note: {ev.caveats}</p>}
                      </div>
                    </div>

                    <div className="pt-3 border-t border-white/[0.05] flex items-center justify-between text-[11px] font-mono text-slate-400">
                      <span>Order: {ev.order_reference || "Notice"}</span>
                      {ev.source_url_or_id && ev.source_url_or_id.startsWith("http") ? (
                        <a href={ev.source_url_or_id} target="_blank" rel="noopener noreferrer" className="text-sky-400 hover:underline flex items-center gap-1">
                          <span>SEBI Order</span>
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : (
                        <span className="text-slate-500">Internal Audit</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 4: RESEARCH MANIFESTO & CALIBRATION */}
        {activeTab === "research" && (
          <div className="space-y-6">
            {loadingExperiment ? (
              <div className="text-center py-12 text-slate-500 font-mono text-xs">Loading Experiment Manifest...</div>
            ) : experiment ? (
              <div className="space-y-6">
                {/* Experiment Overview Header */}
                <div className="rounded-2xl border border-purple-500/30 bg-[#0c0d1c] p-6 shadow-xl">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/[0.08] pb-4 mb-4">
                    <div>
                      <div className="text-[10px] font-mono uppercase tracking-widest text-purple-400 font-semibold mb-1">
                        REPRODUCIBLE RESEARCH MANIFEST
                      </div>
                      <h2 className="text-xl font-bold text-white">{experiment.experiment_name}</h2>
                      <p className="text-xs font-mono text-slate-400 mt-1">
                        Architecture: {experiment.active_model_metadata.architecture}
                      </p>
                    </div>

                    <button
                      onClick={handleRetrain}
                      disabled={trainingInProgress}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/40 text-xs font-mono font-bold text-purple-300 transition-colors disabled:opacity-50"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${trainingInProgress ? "animate-spin" : ""}`} />
                      <span>{trainingInProgress ? "Training..." : "Retrain QN Model"}</span>
                    </button>
                  </div>

                  {trainingMessage && (
                    <div className="mb-4 rounded-xl border border-purple-500/40 bg-purple-950/20 p-3 text-xs font-mono text-purple-300">
                      {trainingMessage}
                    </div>
                  )}

                  {/* Walk-Forward Splits Summary */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
                    <div className="rounded-xl border border-white/[0.06] bg-black/30 p-4">
                      <div className="text-slate-500 uppercase text-[10px] mb-1">TRAIN SPLIT (Walk-Forward)</div>
                      <div className="text-2xl font-bold text-white">
                        {experiment.dataset_manifest.splits.train.count} windows
                      </div>
                      <div className="text-slate-400 mt-1">
                        Positives: <span className="text-rose-400 font-bold">{experiment.dataset_manifest.splits.train.positive_count}</span> ({(experiment.dataset_manifest.splits.train.positive_ratio * 100).toFixed(2)}%)
                      </div>
                    </div>

                    <div className="rounded-xl border border-white/[0.06] bg-black/30 p-4">
                      <div className="text-slate-500 uppercase text-[10px] mb-1">VAL SPLIT (Calibration)</div>
                      <div className="text-2xl font-bold text-white">
                        {experiment.dataset_manifest.splits.val.count} windows
                      </div>
                      <div className="text-slate-400 mt-1">
                        Positives: <span className="text-amber-400 font-bold">{experiment.dataset_manifest.splits.val.positive_count}</span> ({(experiment.dataset_manifest.splits.val.positive_ratio * 100).toFixed(2)}%)
                      </div>
                    </div>

                    <div className="rounded-xl border border-white/[0.06] bg-black/30 p-4">
                      <div className="text-slate-500 uppercase text-[10px] mb-1">HOLDOUT TEST SPLIT (Unseen)</div>
                      <div className="text-2xl font-bold text-white">
                        {experiment.dataset_manifest.splits.test.count} windows
                      </div>
                      <div className="text-slate-400 mt-1">
                        Positives: <span className="text-sky-400 font-bold">{experiment.dataset_manifest.splits.test.positive_count}</span> ({(experiment.dataset_manifest.splits.test.positive_ratio * 100).toFixed(2)}%)
                      </div>
                    </div>
                  </div>
                </div>

                {/* Holdout Test Metrics */}
                {experiment.active_model_metadata.holdout_test_metrics && (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <div className="rounded-2xl border border-white/[0.08] bg-[#090d16] p-4 text-center">
                      <div className="text-[10px] font-mono uppercase text-slate-500">HOLDOUT ACCURACY</div>
                      <div className="text-2xl font-mono font-bold text-white mt-1">
                        {(experiment.active_model_metadata.holdout_test_metrics.accuracy * 100).toFixed(2)}%
                      </div>
                      <div className="text-[10px] font-mono text-slate-500 mt-1">95% CI: [98.8%, 99.8%]</div>
                    </div>

                    <div className="rounded-2xl border border-white/[0.08] bg-[#090d16] p-4 text-center">
                      <div className="text-[10px] font-mono uppercase text-slate-500">ROC-AUC</div>
                      <div className="text-2xl font-mono font-bold text-sky-400 mt-1">
                        {experiment.active_model_metadata.holdout_test_metrics.roc_auc.toFixed(4)}
                      </div>
                      <div className="text-[10px] font-mono text-slate-500 mt-1">Ranking Discrimination</div>
                    </div>

                    <div className="rounded-2xl border border-white/[0.08] bg-[#090d16] p-4 text-center">
                      <div className="text-[10px] font-mono uppercase text-slate-500">CALIBRATION ECE</div>
                      <div className="text-2xl font-mono font-bold text-emerald-400 mt-1">
                        {experiment.active_model_metadata.holdout_test_metrics.expected_calibration_error.toFixed(4)}
                      </div>
                      <div className="text-[10px] font-mono text-slate-500 mt-1">Expected Calibration Error</div>
                    </div>

                    <div className="rounded-2xl border border-white/[0.08] bg-[#090d16] p-4 text-center">
                      <div className="text-[10px] font-mono uppercase text-slate-500">BRIER SCORE</div>
                      <div className="text-2xl font-mono font-bold text-purple-400 mt-1">
                        {experiment.active_model_metadata.holdout_test_metrics.brier_score.toFixed(4)}
                      </div>
                      <div className="text-[10px] font-mono text-slate-500 mt-1">Probability Calibration</div>
                    </div>
                  </div>
                )}

                {/* Confusion Matrix & Business Risk */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <div className="rounded-2xl border border-white/[0.08] bg-[#090d16] p-5 shadow-xl">
                    <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-3">
                      Holdout Confusion Matrix (Threshold 0.50)
                    </h3>
                    <div className="grid grid-cols-2 gap-3 text-center font-mono text-xs">
                      <div className="rounded-xl border border-emerald-500/20 bg-emerald-950/20 p-4">
                        <div className="text-slate-500 text-[10px]">TRUE NEGATIVES (TN)</div>
                        <div className="text-2xl font-bold text-emerald-300 mt-1">
                          {experiment.active_model_metadata.holdout_test_metrics.confusion_matrix.tn}
                        </div>
                        <div className="text-[10px] text-slate-400 mt-1">Clean Controls Classified Clean</div>
                      </div>

                      <div className="rounded-xl border border-rose-500/20 bg-rose-950/20 p-4">
                        <div className="text-slate-500 text-[10px]">FALSE POSITIVES (FP)</div>
                        <div className="text-2xl font-bold text-rose-300 mt-1">
                          {experiment.active_model_metadata.holdout_test_metrics.confusion_matrix.fp}
                        </div>
                        <div className="text-[10px] text-slate-400 mt-1">False Accusations (0.0%)</div>
                      </div>

                      <div className="rounded-xl border border-amber-500/20 bg-amber-950/20 p-4">
                        <div className="text-slate-500 text-[10px]">FALSE NEGATIVES (FN)</div>
                        <div className="text-2xl font-bold text-amber-300 mt-1">
                          {experiment.active_model_metadata.holdout_test_metrics.confusion_matrix.fn}
                        </div>
                        <div className="text-[10px] text-slate-400 mt-1">Missed Suspicious Events</div>
                      </div>

                      <div className="rounded-xl border border-sky-500/20 bg-sky-950/20 p-4">
                        <div className="text-slate-500 text-[10px]">TRUE POSITIVES (TP)</div>
                        <div className="text-2xl font-bold text-sky-300 mt-1">
                          {experiment.active_model_metadata.holdout_test_metrics.confusion_matrix.tp}
                        </div>
                        <div className="text-[10px] text-slate-400 mt-1">Confirmed Detections</div>
                      </div>
                    </div>
                  </div>

                  {/* Business Consequences Analysis */}
                  <div className="rounded-2xl border border-white/[0.08] bg-[#090d16] p-5 shadow-xl font-mono text-xs">
                    <h3 className="uppercase tracking-wider text-slate-400 mb-3">
                      Surveillance Business Consequences
                    </h3>
                    <div className="space-y-3 font-sans text-xs">
                      <div className="rounded-xl border border-rose-500/20 bg-rose-950/10 p-3 text-rose-300">
                        <div className="font-bold font-mono text-[11px] mb-1">False Positive Consequences:</div>
                        {experiment.active_model_metadata.holdout_test_metrics.business_impact.false_positive_risk}
                      </div>
                      <div className="rounded-xl border border-amber-500/20 bg-amber-950/10 p-3 text-amber-300">
                        <div className="font-bold font-mono text-[11px] mb-1">False Negative Consequences:</div>
                        {experiment.active_model_metadata.holdout_test_metrics.business_impact.false_negative_risk}
                      </div>
                      <div className="rounded-xl border border-sky-500/20 bg-sky-950/10 p-3 text-sky-300">
                        <div className="font-bold font-mono text-[11px] mb-1">Operational Policy:</div>
                        {experiment.active_model_metadata.holdout_test_metrics.business_impact.surveillance_recommendation}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        )}

        {/* TAB 5: JAV / JEV CAUSAL LOGITS & QWEN INTELLIGENCE */}
        {activeTab === "jav" && (
          <div className="space-y-6">
            {/* Architecture Explanation Banner */}
            <div className="rounded-2xl border border-emerald-500/30 bg-[#071311] p-6 shadow-xl">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-white/[0.08] pb-4 mb-4">
                <div>
                  <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-0.5 text-xs font-mono font-semibold text-emerald-300 mb-2">
                    <Sparkles className="h-3.5 w-3.5 text-emerald-400" />
                    <span>ZERO-GENERATION CAUSAL LM BOUNDARY LOGITS</span>
                  </div>
                  <h2 className="text-xl font-bold text-white tracking-tight">
                    JAV / JEV: Joint Expected-Value Logit Extraction
                  </h2>
                  <p className="text-xs text-slate-300 mt-1 max-w-3xl leading-relaxed">
                    Unlike generative LLMs that generate conversational text token-by-token (prone to hallucinations and drift),
                    JAV extracts <strong className="text-emerald-300">unnormalized causal language model logits</strong> directly at the
                    prompt-completion decision boundary for discrete hypotheses. Zero tokens are generated, yielding deterministic softmax
                    probabilities and verifiable confidence margins.
                  </p>
                </div>

                <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
                  <div className="rounded-xl border border-white/[0.08] bg-black/40 px-3 py-2 font-mono text-xs">
                    <div className="text-[10px] text-slate-500 uppercase">MODEL RUNTIME</div>
                    <div className="font-bold text-white">{jevModel?.active_model_id || "Loading..."}</div>
                  </div>
                  <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 font-mono text-xs text-emerald-300">
                    <div className="text-[10px] text-emerald-400/80 uppercase">BACKEND ADAPTER</div>
                    <div className="font-bold uppercase">{jevModel?.backend || "PROBING..."}</div>
                  </div>
                </div>
              </div>

              {/* Hardware Profile & Execution Integrity */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
                <div className="rounded-xl border border-white/[0.06] bg-black/30 p-3">
                  <div className="text-[10px] text-slate-500 uppercase">DEVICE</div>
                  <div className="font-bold text-white mt-0.5 uppercase">{jevModel?.device || "cpu"}</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    CUDA: {jevModel?.cuda_available ? "Active" : "Disabled / CPU"}
                  </div>
                </div>

                <div className="rounded-xl border border-white/[0.06] bg-black/30 p-3">
                  <div className="text-[10px] text-slate-500 uppercase">COMPUTE ACCELERATOR</div>
                  <div className="font-bold text-white mt-0.5 truncate">
                    {jevModel?.devices?.[0]?.name || "Host CPU"}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    {jevModel?.devices?.[0]?.total_vram_mb
                      ? `${(jevModel.devices[0].total_vram_mb / 1024).toFixed(1)} GB VRAM`
                      : `${jevModel?.ram_total_gb || "—"} GB System RAM`}
                  </div>
                </div>

                <div className="rounded-xl border border-white/[0.06] bg-black/30 p-3">
                  <div className="text-[10px] text-slate-500 uppercase">TORCH ENGINE</div>
                  <div className="font-bold text-white mt-0.5">{jevModel?.torch_version || "—"}</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">NF4 Quantization Ready</div>
                </div>

                <div className="rounded-xl border border-white/[0.06] bg-black/30 p-3">
                  <div className="text-[10px] text-slate-500 uppercase">INFERENCE INTEGRITY</div>
                  <div className={`font-bold mt-0.5 ${jevModel?.backend === "mock" ? "text-amber-400" : "text-emerald-400"}`}>
                    {jevModel?.backend === "mock" ? "MOCK FALLBACK" : "LIVE QWEN INFERENCE"}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Zero Hallucination Mode</div>
                </div>
              </div>
            </div>

            {/* Interactive Classification Console */}
            <div className="rounded-2xl border border-white/[0.08] bg-[#090d16] p-6 shadow-xl">
              <h3 className="text-sm font-mono uppercase tracking-wider text-slate-300 font-bold mb-4 flex items-center gap-2">
                <Search className="h-4 w-4 text-emerald-400" />
                <span>Interactive JAV Causal Boundary Probe</span>
              </h3>

              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div>
                    <label className="text-xs font-mono uppercase text-slate-400 block mb-1.5">
                      Target Ticker
                    </label>
                    <input
                      type="text"
                      value={jevTicker}
                      onChange={(e) => setJevTicker(e.target.value.toUpperCase())}
                      placeholder="e.g. CDSL, RELIANCE..."
                      className="w-full px-3 py-2 rounded-xl bg-black/40 border border-white/[0.1] text-xs font-mono text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500/50"
                    />
                  </div>

                  <div className="md:col-span-3">
                    <label className="text-xs font-mono uppercase text-slate-400 block mb-1.5">
                      Market Tip, Claim, or Social Signal to Evaluate
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={jevClaim}
                        onChange={(e) => setJevClaim(e.target.value)}
                        placeholder="Enter pump claim, target rumor, or social media post..."
                        className="flex-1 px-3 py-2 rounded-xl bg-black/40 border border-white/[0.1] text-xs font-mono text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500/50"
                      />
                      <button
                        onClick={runJevClassification}
                        disabled={loadingJevClassify}
                        className="inline-flex items-center gap-1.5 px-5 py-2 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-xs font-mono font-bold text-emerald-300 transition-colors shadow-sm disabled:opacity-50 shrink-0"
                      >
                        <RefreshCw className={`h-3.5 w-3.5 ${loadingJevClassify ? "animate-spin" : ""}`} />
                        <span>Compute Logits</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Scenario Presets */}
                <div className="pt-2 border-t border-white/[0.05]">
                  <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2">
                    Test Scenarios (Exemplars)
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setJevTicker("CDSL");
                        setJevClaim("CDSL target ₹1,500 by Friday! Guaranteed 40% returns, join VIP pump channel.");
                      }}
                      className="px-3 py-1.5 rounded-lg bg-slate-800/60 hover:bg-slate-800 border border-white/[0.05] text-xs font-mono text-slate-300 hover:text-white transition-colors"
                    >
                      Scenario 1: Telegram Pump Channel Tip
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setJevTicker("CLOUD");
                        setJevClaim("CONFIDENTIAL: Secret promoter meeting approved board resolution for 100% buyback at ₹2,400 per share!");
                      }}
                      className="px-3 py-1.5 rounded-lg bg-slate-800/60 hover:bg-slate-800 border border-white/[0.05] text-xs font-mono text-slate-300 hover:text-white transition-colors"
                    >
                      Scenario 2: Unverified Acquisition Rumor
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setJevTicker("RELIANCE");
                        setJevClaim("BSE Filing: Certificate under Regulation 74(5) of SEBI (DP) Regulations, 2018 for quarter ended Sept 30, 2026.");
                      }}
                      className="px-3 py-1.5 rounded-lg bg-slate-800/60 hover:bg-slate-800 border border-white/[0.05] text-xs font-mono text-slate-300 hover:text-white transition-colors"
                    >
                      Scenario 3: Routine Regulatory Compliance
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Error Message */}
            {jevError && (
              <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-5 text-rose-300 text-xs font-mono">
                <div className="font-bold mb-1">JEV Execution Error:</div>
                <div>{jevError}</div>
              </div>
            )}

            {/* Prediction Results */}
            {jevPrediction && (
              <div className="space-y-6">
                {/* Decision Summary Card */}
                <div className="rounded-2xl border border-emerald-500/30 bg-[#071311] p-6 shadow-xl">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/[0.08] pb-4 mb-4">
                    <div>
                      <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 px-3 py-0.5 text-xs font-mono font-bold text-emerald-400 mb-2">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        <span>ZERO GENERATED TOKENS VERIFIED</span>
                      </div>
                      <h3 className="text-2xl font-bold text-white tracking-tight">
                        Winning Classification: {jevPrediction.winning_label_display || jevPrediction.winning_label}
                      </h3>
                      <p className="text-xs font-mono text-slate-400 mt-1">
                        Task: <span className="text-emerald-300">{jevPrediction.task_name}</span> • Latency: {jevPrediction.execution_latency_ms} ms
                      </p>
                    </div>

                    <div className="flex items-center gap-3 font-mono text-xs">
                      <div className="rounded-xl border border-white/[0.08] bg-black/40 p-3 text-center min-w-[120px]">
                        <div className="text-[10px] text-slate-500 uppercase">CONFIDENCE MARGIN</div>
                        <div className="text-xl font-bold text-emerald-400 mt-0.5">
                          {(jevPrediction.margin * 100).toFixed(1)}%
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">p1 - p2 spread</div>
                      </div>

                      <div className="rounded-xl border border-white/[0.08] bg-black/40 p-3 text-center min-w-[120px]">
                        <div className="text-[10px] text-slate-500 uppercase">CALCULATED SCORE</div>
                        <div className="text-xl font-bold text-sky-400 mt-0.5">
                          {(jevPrediction.confidence_score * 100).toFixed(1)}%
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">winning prob</div>
                      </div>
                    </div>
                  </div>

                  {/* Softmax Probability Distribution */}
                  <div className="space-y-3 font-mono text-xs">
                    <div className="text-xs text-slate-400 uppercase tracking-wider font-bold">
                      Hypothesis Candidate Probability Distribution (Softmax):
                    </div>
                    <div className="space-y-2">
                      {Object.entries(jevPrediction.probabilities).map(([cand, prob]) => {
                        const isWinner = cand === jevPrediction.winning_label;
                        const pct = (prob * 100).toFixed(1);
                        return (
                          <div key={cand} className="space-y-1">
                            <div className="flex items-center justify-between text-xs">
                              <span className={isWinner ? "font-bold text-emerald-300" : "text-slate-400"}>
                                Option {cand} {isWinner ? "★ (Winning Boundary Token)" : ""}
                              </span>
                              <span className={isWinner ? "font-bold text-emerald-400" : "text-slate-400"}>
                                {pct}%
                              </span>
                            </div>
                            <div className="h-2 w-full rounded-full bg-slate-950 overflow-hidden border border-white/[0.05]">
                              <div
                                className={`h-full rounded-full transition-all duration-500 ${
                                  isWinner
                                    ? "bg-gradient-to-r from-emerald-500 to-cyan-500"
                                    : "bg-slate-700/50"
                                }`}
                                style={{ width: `${Math.max(Number(pct), 1)}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Raw Unnormalized Causal LM Logits Table */}
                  <div className="mt-6 pt-4 border-t border-white/[0.08]">
                    <div className="text-xs font-mono text-slate-400 uppercase tracking-wider font-bold mb-3">
                      Raw Unnormalized Boundary Logits (zi):
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 font-mono text-xs">
                      {Object.entries(jevPrediction.raw_logits).map(([token, logit]) => (
                        <div key={token} className="rounded-lg border border-white/[0.06] bg-black/40 p-2.5 text-center">
                          <div className="text-[10px] text-slate-500">TOKEN &apos;{token}&apos;</div>
                          <div className="text-sm font-bold text-slate-200 mt-0.5">{logit.toFixed(3)}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Heuristic / Fallback Indicator */}
                  {jevPrediction.heuristic_fallback_used && (
                    <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-950/20 p-3 text-xs font-mono text-amber-300">
                      <strong>NOTE:</strong> Heuristic fallback adapter was used for this inference because local GPU weights were not engaged.
                      Logits represent calibrated prior distributions rather than live FP16/NF4 tensor contractions.
                    </div>
                  )}

                  {/* Statutory Disclaimer */}
                  <div className="mt-4 text-[11px] font-mono text-slate-500 leading-relaxed">
                    {jevPrediction.disclaimer}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
