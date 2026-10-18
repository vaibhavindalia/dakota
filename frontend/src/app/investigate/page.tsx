"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import { 
  Radio, 
  ShieldAlert, 
  Sparkles, 
  Filter, 
  ExternalLink, 
  AlertTriangle, 
  Layers, 
  Clock, 
  CheckCircle2, 
  Search,
  Eye,
  Activity
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Provider = {
  status?: string;
  provider?: string;
  result_count?: number;
  results?: any[];
  messages?: any[];
  observations?: { signal?: string; severity?: string; text?: string }[];
  error?: string | null;
  sentiment?: Record<string, any>;
  message_volume?: Record<string, any>;
  query?: string;
  article_count?: number;
  hype_article_count?: number;
  red_flag_article_count?: number;
};

type Risk = {
  score: number;
  band: string;
  raw_score?: number;
  available_score_points?: number;
  components?: Record<string, number>;
  reasons?: string[];
  method?: string;
  disclaimer?: string;
};

type LiveItem = {
  investigation_id: string;
  captured_at?: string;
  telegram_timestamp?: string | null;
  channel?: string;
  channel_username?: string | null;
  message_id?: number;
  ticker?: string | null;
  tickers?: string[];
  price_target?: number | null;
  n_scam_markers?: number;
  urgency?: boolean;
  classification?: {
    message_type?: string;
    market_domain?: string;
    domain?: string;
    topic?: string | null;
    tickers?: string[];
    confidence?: number;
    trading_intent?: boolean;
    method?: string;
  };
  impact?: {
    status?: string;
    domain?: string;
    entity?: string | null;
    exact_topic?: string | null;
    matched_text?: string | null;
    potentially_affected_areas?: string[];
    investigation_targets?: string[];
    rationale?: string;
  };
  investigation?: {
    status?: string;
    investigation_mode?: string;
    risk?: Risk | null;
    evidence?: any;
    market?: any;
    investigations?: any[];
    next_steps?: string[];
    disclaimer?: string;
    risk_engine_status?: {
      status?: string;
      method?: string;
      tickers_scored?: string[];
      as_of?: string;
    };
  };
  risk?: Risk | null;
  status?: string;
  disclaimer?: string;
};

type ManualResult = any;

type SourceStatus = {
  key: string;
  label: string;
  status: string;
  detail: string;
};

function human(v?: string | null) {
  return (v || "—")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function fmt(v: unknown, digits = 0) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function timeAgo(value?: string | null) {
  if (!value) return "unknown time";
  const ms = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(ms)) return "unknown time";
  const mins = Math.max(0, Math.floor(ms / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function statusTone(status?: string) {
  const s = (status || "").toLowerCase();
  if (["connected", "success", "rss_fallback", "ingestion_connector", "ingestion_source", "testing_phase", "testing_phases", "in_testing_phase"].includes(s)) {
    return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-200";
  }
  if (["no_results", "rate_limited", "missing_credentials", "not_configured", "disabled", "connector_required"].includes(s)) {
    return "border-amber-400/20 bg-amber-400/[0.05] text-amber-200";
  }
  if (s === "error" || s === "unauthorized" || s === "forbidden" || s === "provider_unavailable" || s === "timeout") {
    return "border-red-400/20 bg-red-400/[0.05] text-red-200";
  }
  return "border-white/10 bg-white/[0.03] text-white/50";
}

function scoreTone(band?: string) {
  const b = (band || "").toLowerCase();
  if (b.includes("high")) return "border-red-400/30 bg-red-400/[0.08] text-red-100";
  if (b.includes("elev")) return "border-amber-400/30 bg-amber-400/[0.08] text-amber-100";
  return "border-emerald-400/25 bg-emerald-400/[0.07] text-emerald-100";
}

function RiskBadge({ risk }: { risk?: Risk | null }) {
  if (!risk) {
    return <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-white/35">No score</span>;
  }
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${scoreTone(risk.band)}`}>
      {fmt(risk.score)} · {risk.band}
    </span>
  );
}

function SmallStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.025] p-4">
      <div className="text-[10px] uppercase tracking-[0.2em] text-white/30">{label}</div>
      <div className="mt-2 text-sm font-semibold text-white">{value}</div>
    </div>
  );
}

function ProviderPill({ provider }: { provider: SourceStatus }) {
  const isInstagram = provider.key?.toLowerCase() === "instagram" || provider.label?.toLowerCase() === "instagram";
  const displayStatus = isInstagram ? "testing_phases" : provider.status;

  return (
    <div className={`rounded-xl border px-3 py-2 ${statusTone(displayStatus)}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold text-white/80">{provider.label}</span>
        <span className="h-2 w-2 rounded-full bg-current opacity-80" />
      </div>
      <div className="mt-1 text-[11px] opacity-70">{human(displayStatus)}</div>
    </div>
  );
}

function getRisk(item: LiveItem) {
  return item.risk || item.investigation?.risk || null;
}

function getEvidence(item: LiveItem) {
  return item.investigation?.evidence || {};
}

function getProviders(item: LiveItem | null): SourceStatus[] {
  if (!item) return [];
  const evidence = getEvidence(item);
  const social = evidence.social || {};
  const news: Provider = evidence.news || {};
  const reddit: Provider = social.reddit || {};
  const x: Provider = social.x || {};
  const instagram: Provider = social.instagram || {};
  const stocktwits: Provider = social.stocktwits || {};
  return [
    {
      key: "news",
      label: "News",
      status: news.status || "unknown",
      detail: news.article_count != null ? `${news.article_count} articles` : "Coverage unavailable",
    },
    {
      key: "reddit",
      label: "Reddit",
      status: reddit.status || "unknown",
      detail: reddit.result_count != null ? `${reddit.result_count} results` : "Coverage unavailable",
    },
    {
      key: "x",
      label: "X",
      status: x.status || "unknown",
      detail: x.result_count != null ? `${x.result_count} posts` : "Provider not connected",
    },
    {
      key: "instagram",
      label: "Instagram",
      status: "testing_phases",
      detail: instagram.result_count != null ? `${instagram.result_count} media` : "Active in testing phase",
    },
    {
      key: "stocktwits",
      label: "StockTwits",
      status: stocktwits.status || "unknown",
      detail: stocktwits.result_count != null ? `${stocktwits.result_count} results` : "Provider not connected",
    },
  ];
}

function FeedCard({ item, onOpen }: { item: LiveItem; onOpen: (item: LiveItem) => void }) {
  const risk = getRisk(item);
  const cls = item.classification;
  const impact = item.impact;
  const ticker = impact?.entity || item.ticker || item.tickers?.[0] || "Market topic";
  const isScored = Boolean(risk);

  return (
    <button
      onClick={() => onOpen(item)}
      className="w-full rounded-2xl border border-white/10 bg-white/[0.025] p-5 text-left transition hover:border-sky-400/25 hover:bg-white/[0.04]"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold text-white">{human(ticker)}</span>
            <RiskBadge risk={risk} />
          </div>
          <div className="mt-1 text-xs text-white/35">
            {item.channel_username || item.channel || "Telegram"} · {timeAgo(item.telegram_timestamp || item.captured_at)}
          </div>
        </div>
        <div className="text-xs text-white/25">#{item.message_id ?? "—"}</div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <SmallStat label="Message type" value={cls?.message_type || "—"} />
        <SmallStat label="Domain" value={human(cls?.market_domain || cls?.domain)} />
        <SmallStat label="Impact" value={human(impact?.exact_topic || impact?.entity)} />
        <SmallStat label={isScored ? "Risk status" : "Classification"} value={isScored ? risk?.band || "—" : human(impact?.status || item.status)} />
      </div>

      {risk?.reasons?.length ? (
        <div className="mt-4 rounded-xl border border-white/10 bg-black/10 p-3 text-xs text-white/55">
          <div className="mb-1 text-[10px] uppercase tracking-[0.2em] text-white/25">Why it moved</div>
          {risk.reasons.slice(0, 2).join(" • ")}
        </div>
      ) : null}
    </button>
  );
}

function ProviderDetail({ label, provider }: { label: string; provider?: Provider }) {
  const p = provider || {};
  const isInstagram = label.toLowerCase() === "instagram";
  const status = isInstagram ? "testing_phases" : (p.status || "unknown");
  const count = p.result_count ?? (Array.isArray(p.results) ? p.results.length : undefined);
  const observations = p.observations || [];
  const error = isInstagram ? null : p.error;

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="font-semibold text-white/90">{label}</div>
        <span className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold ${statusTone(status)}`}>
          {human(status)}
        </span>
      </div>
      <div className="mt-3 text-xs text-white/45">
        {count != null ? `${count} result${count === 1 ? "" : "s"}` : "No result count available"}
      </div>
      {error ? <div className="mt-3 rounded-lg bg-red-400/[0.06] p-3 text-xs text-red-100/70">{error}</div> : null}
      {isInstagram && (
        <div className="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06] p-3 text-xs text-emerald-200/90 flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span>Instagram hashtag discovery adapter is active in testing phase.</span>
        </div>
      )}
      {observations.slice(0, 2).map((obs, index) => (
        <div key={`${obs.signal || "obs"}-${index}`} className="mt-3 text-xs text-white/50">• {obs.text}</div>
      ))}
    </div>
  );
}

function ManualSummary({ manual }: { manual: ManualResult }) {
  const investigation = manual?.investigations?.[0];
  const risk: Risk | null = manual?.risk || investigation?.risk || manual?.stock_verdicts?.[0] || null;
  const evidence = manual?.evidence || investigation?.evidence || {};
  const social = evidence.social || {};
  const sentiment = social.bulk_sentiment_analysis || {};
  const ticker = manual?.ticker || investigation?.ticker || manual?.tip?.tickers?.[0] || "Investigation";

  if (!risk) {
    return (
      <div className="rounded-2xl border border-amber-400/20 bg-amber-400/[0.04] p-5 text-sm text-amber-100/80">
        Dakota classified this message, but no numeric risk score is available for the resolved entity yet.
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className={`rounded-2xl border p-5 ${scoreTone(risk.band)}`}>
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="text-xs uppercase tracking-[0.22em] opacity-65">Dakota assessment</div>
            <div className="mt-2 text-3xl font-bold">{human(String(ticker))}</div>
            <div className="mt-1 text-sm opacity-65">Explainable risk aggregation</div>
          </div>
          <div className="text-right">
            <div className="text-5xl font-bold">{fmt(risk.score)}</div>
            <div className="text-sm opacity-70">/100 · {risk.band}</div>
          </div>
        </div>
      </div>

      {risk.components ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {Object.entries(risk.components).map(([key, value]) => (
            <SmallStat key={key} label={human(key)} value={fmt(value, 1)} />
          ))}
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <ProviderDetail label="News" provider={evidence.news} />
        <ProviderDetail label="Reddit" provider={social.reddit} />
        <ProviderDetail label="X" provider={social.x} />
        <ProviderDetail label="Instagram" provider={social.instagram} />
        <ProviderDetail label="StockTwits" provider={social.stocktwits} />
        <ProviderDetail label="Telegram" provider={social.telegram} />
      </div>

      <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
        <div className="flex items-center justify-between">
          <div className="font-semibold">Social sentiment</div>
          <span className={`rounded-full border px-2.5 py-1 text-[10px] ${statusTone(sentiment.status)}`}>{human(sentiment.status || "unknown")}</span>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-4">
          <SmallStat label="Positive" value={String(sentiment.positive ?? 0)} />
          <SmallStat label="Neutral" value={String(sentiment.neutral ?? 0)} />
          <SmallStat label="Negative" value={String(sentiment.negative ?? 0)} />
          <SmallStat label="Total" value={String(sentiment.total ?? 0)} />
        </div>
      </div>

      {risk.reasons?.length ? (
        <div>
          <div className="mb-3 text-sm font-semibold">Evidence / indicators</div>
          <div className="grid gap-2 md:grid-cols-2">
            {risk.reasons.map((reason) => <div key={reason} className="rounded-xl border border-white/10 p-3 text-sm text-white/60">{reason}</div>)}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function DetailPanel({ item, onClose }: { item: LiveItem; onClose: () => void }) {
  const risk = getRisk(item);
  const evidence = getEvidence(item);
  const social = evidence.social || {};
  const sentiment = social.bulk_sentiment_analysis || {};
  const providers = getProviders(item);
  const target = item.impact?.entity || item.ticker || item.tickers?.[0] || "Market topic";

  return (
    <div className="fixed inset-0 z-50 bg-black/75 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="mx-auto mt-6 max-h-[90vh] max-w-6xl overflow-y-auto rounded-3xl border border-white/10 bg-[#0a0f18] p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="text-xs uppercase tracking-[0.25em] text-sky-400">Investigation detail</div>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h2 className="text-3xl font-bold">{human(target)}</h2>
              <RiskBadge risk={risk} />
            </div>
            <div className="mt-1 text-sm text-white/35">{item.channel_username || item.channel || "Telegram"} · {item.investigation_id}</div>
          </div>
          <button onClick={onClose} className="rounded-xl border border-white/10 px-4 py-2 text-sm text-white/55 hover:text-white">Close</button>
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <SmallStat label="Message type" value={item.classification?.message_type || "—"} />
          <SmallStat label="Domain" value={human(item.classification?.market_domain || item.classification?.domain)} />
          <SmallStat label="Impact" value={human(item.impact?.exact_topic || item.impact?.entity)} />
          <SmallStat label="Confidence" value={item.classification?.confidence == null ? "—" : `${fmt(item.classification.confidence * 100, 1)}%`} />
        </div>

        <div className="mt-6">
          <div className="mb-3 text-sm font-semibold">Source coverage</div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {providers.map((provider) => <ProviderPill key={provider.key} provider={provider} />)}
          </div>
        </div>

        {risk ? (
          <div className={`mt-6 rounded-2xl border p-5 ${scoreTone(risk.band)}`}>
            <div className="text-xs uppercase tracking-[0.22em] opacity-60">Risk aggregation</div>
            <div className="mt-2 flex items-end gap-3">
              <span className="text-5xl font-bold">{fmt(risk.score)}</span>
              <span className="mb-2 text-sm opacity-70">/100 · {risk.band}</span>
            </div>
            <div className="mt-2 text-xs opacity-55">{risk.method || "Dakota explainable risk engine"}</div>
          </div>
        ) : null}

        {risk?.components ? (
          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {Object.entries(risk.components).map(([key, value]) => <SmallStat key={key} label={human(key)} value={fmt(value, 1)} />)}
          </div>
        ) : null}

        {risk?.reasons?.length ? (
          <div className="mt-6">
            <div className="mb-3 text-sm font-semibold">Why Dakota raised the score</div>
            <div className="grid gap-2 md:grid-cols-2">{risk.reasons.map((reason) => <div key={reason} className="rounded-xl border border-white/10 p-3 text-sm text-white/60">{reason}</div>)}</div>
          </div>
        ) : null}

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <ProviderDetail label="News" provider={evidence.news} />
          <ProviderDetail label="Reddit" provider={social.reddit} />
          <ProviderDetail label="X" provider={social.x} />
          <ProviderDetail label="Instagram" provider={social.instagram} />
          <ProviderDetail label="StockTwits" provider={social.stocktwits} />
          <ProviderDetail label="Telegram" provider={social.telegram} />
        </div>

        <div className="mt-6 rounded-2xl border border-white/10 p-5">
          <div className="flex items-center justify-between">
            <div className="font-semibold">Social sentiment</div>
            <span className={`rounded-full border px-2.5 py-1 text-[10px] ${statusTone(sentiment.status)}`}>{human(sentiment.status || "unknown")}</span>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-4">
            <SmallStat label="Positive" value={String(sentiment.positive ?? 0)} />
            <SmallStat label="Neutral" value={String(sentiment.neutral ?? 0)} />
            <SmallStat label="Negative" value={String(sentiment.negative ?? 0)} />
            <SmallStat label="Total" value={String(sentiment.total ?? 0)} />
          </div>
        </div>

        {evidence.news?.articles?.length ? (
          <div className="mt-6 rounded-2xl border border-white/10 p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="font-semibold">Recent news</div>
              <div className="text-xs text-white/35">{evidence.news.articles.length} shown</div>
            </div>
            <div className="mt-4 space-y-2">
              {evidence.news.articles.slice(0, 6).map((article: any, index: number) => (
                <a key={`${article.url || article.link || article.title || article.headline || "article"}-${index}`} href={article.url || article.link} target="_blank" rel="noreferrer" className="block rounded-xl border border-white/10 p-3 hover:bg-white/[0.025]">
                  <div className="text-sm text-white/80">{article.title || article.headline || "Untitled article"}</div>
                  <div className="mt-1 text-xs text-white/35">{article.domain || article.source || article.provider || "Source"}</div>
                </a>
              ))}
            </div>
          </div>
        ) : null}

        {item.impact?.rationale ? <div className="mt-6 rounded-xl border border-sky-400/15 bg-sky-400/[0.04] p-4 text-sm text-white/60">{item.impact.rationale}</div> : null}
        <div className="mt-6 text-xs leading-5 text-white/30">Dakota reports risk indicators from available evidence. It does not determine fraud and does not provide buy/sell advice.</div>
      </div>
    </div>
  );
}

export default function InvestigatePage() {
  const [tip, setTip] = useState("");
  const [source, setSource] = useState("manual");
  const [manual, setManual] = useState<ManualResult | null>(null);
  const [live, setLive] = useState<LiveItem[]>([]);
  const [selected, setSelected] = useState<LiveItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [liveError, setLiveError] = useState("");
  const [manualError, setManualError] = useState("");

  async function refreshLive() {
    try {
      const response = await fetch(`${API}/api/investigations/live?limit=50`, { cache: "no-store" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Live feed unavailable");
      setLive(body.items || []);
      setLiveError("");
    } catch (err) {
      setLiveError(err instanceof Error ? err.message : "Live feed unavailable");
    }
  }

  useEffect(() => {
    refreshLive();
    const timer = window.setInterval(refreshLive, 3000);
    return () => window.clearInterval(timer);
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setManualError("");
    try {
      const response = await fetch(`${API}/api/investigate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tip, source }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Investigation failed");
      setManual(body);
    } catch (err) {
      setManualError(err instanceof Error ? err.message : "Investigation failed");
    } finally {
      setLoading(false);
    }
  }

  const scored = useMemo(() => live.filter((item) => Boolean(getRisk(item))), [live]);
  const classified = useMemo(() => live.filter((item) => !getRisk(item)), [live]);
  const latestScored = scored[0] || null;
  const providerStatuses = getProviders(latestScored);

  return (
    <main className="min-h-screen bg-[#05070a] text-slate-100 flex flex-col bg-terminal-grid">
      <Navbar />

      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 sm:py-12 flex-1">
        <header className="mb-8">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/[0.08] pb-6">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-mono font-semibold text-cyan-300 mb-3">
                <Radio className="h-3.5 w-3.5" />
                <span>REAL-TIME FORENSIC INTELLIGENCE WIRE</span>
              </div>
              <h1 className="text-3xl sm:text-4xl font-black text-white">
                Live Evidence Terminal
              </h1>
              <p className="mt-2 max-w-2xl text-sm text-slate-400">
                Multi-channel intake → classification → exact company impact → news &amp; social footprint → explainable risk scoring.
              </p>
            </div>

            <div className="flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-mono font-semibold text-emerald-300">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span>LIVE WIRE POLLING (3s)</span>
            </div>
          </div>
        </header>

        <section className="mb-8 rounded-2xl border border-white/[0.08] bg-[#0a0e17] p-5 sm:p-6 shadow-xl">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.22em] text-white/30">Source coverage</div>
              <div className="mt-1 text-lg font-semibold">Connected intelligence layer</div>
              <div className="mt-1 text-xs text-white/35">Provider gaps are surfaced explicitly.</div>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {providerStatuses.length ? providerStatuses.map((provider) => <ProviderPill key={provider.key} provider={provider} />) : (
                ["News", "Reddit", "X", "Instagram", "StockTwits"].map((label) => (
                  <ProviderPill key={label.toLowerCase()} provider={{ key: label.toLowerCase(), label, status: label === "Instagram" ? "testing_phases" : "unknown", detail: label === "Instagram" ? "Active in testing phase" : "Waiting for a scored investigation" }} />
                ))
              )}
            </div>
          </div>
        </section>

        <section className="mt-6 rounded-3xl border border-sky-400/15 bg-sky-400/[0.025] p-5 sm:p-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.22em] text-sky-300/70">Latest scored investigation</div>
              <div className="mt-2 text-2xl font-bold">{latestScored ? human(latestScored.impact?.entity || latestScored.ticker || "Investigation") : "Waiting for a scored investigation"}</div>
              <div className="mt-1 text-sm text-white/35">{latestScored ? `${latestScored.channel_username || latestScored.channel || "Telegram"} · ${timeAgo(latestScored.telegram_timestamp || latestScored.captured_at)}` : "Send a tip or wait for the next Telegram investigation."}</div>
            </div>
            {latestScored ? <RiskBadge risk={getRisk(latestScored)} /> : null}
          </div>
          {latestScored ? (
            <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <SmallStat label="Message type" value={latestScored.classification?.message_type || "—"} />
              <SmallStat label="Domain" value={human(latestScored.classification?.market_domain || latestScored.classification?.domain)} />
              <SmallStat label="Impact" value={human(latestScored.impact?.exact_topic || latestScored.impact?.entity)} />
              <SmallStat label="Source" value={latestScored.channel_username || latestScored.channel || "Telegram"} />
            </div>
          ) : null}
        </section>

        <section className="mt-6 rounded-3xl border border-white/10 bg-white/[0.025] p-5 sm:p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">Manual investigation</div>
              <div className="mt-1 text-xs text-white/30">Run the same investigation path used by the live pipeline.</div>
            </div>
            <div className="text-xs text-white/25">No raw message is stored by the intake layer.</div>
          </div>
          <form onSubmit={submit} className="flex flex-col gap-4 xl:flex-row">
            <textarea value={tip} onChange={(e) => setTip(e.target.value)} required rows={5} placeholder="CDSL target 1500 tomorrow..." className="min-h-32 flex-1 resize-y rounded-2xl border border-white/10 bg-black/20 p-4 text-sm outline-none placeholder:text-white/20 focus:border-sky-400/40" />
            <div className="w-full xl:w-56">
              <label className="text-xs uppercase tracking-widest text-white/35">Source</label>
              <select value={source} onChange={(e) => setSource(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-[#101521] px-3 py-3 text-sm">
                <option value="manual">Manual</option>
                <option value="telegram">Telegram</option>
                <option value="whatsapp">WhatsApp</option>
                <option value="x">X</option>
                <option value="reddit">Reddit</option>
                <option value="instagram">Instagram</option>
              </select>
              <button disabled={loading} className="mt-3 w-full rounded-xl bg-sky-500 px-4 py-3 font-semibold text-slate-950 transition hover:bg-sky-400 disabled:opacity-50">
                {loading ? "Investigating…" : "Investigate"}
              </button>
            </div>
          </form>
          {manualError ? <div className="mt-4 rounded-xl border border-red-400/20 bg-red-400/[0.05] p-3 text-sm text-red-100">{manualError}</div> : null}
        </section>

        {manual ? (
          <section className="mt-6 rounded-3xl border border-white/10 bg-white/[0.025] p-5 sm:p-6">
            <div className="mb-5">
              <div className="text-sm font-semibold">Manual result</div>
              <div className="mt-1 text-xs text-white/30">Rendered from the investigation result — raw JSON is intentionally hidden.</div>
            </div>
            <ManualSummary manual={manual} />
          </section>
        ) : null}

        <section className="mt-10">
          <div className="mb-4 flex items-end justify-between">
            <div>
              <div className="text-sm font-semibold">Live investigations</div>
              <div className="mt-1 text-xs text-white/30">Only investigations with a numeric risk score are promoted to the main feed.</div>
            </div>
            <div className="text-xs text-white/30">{scored.length} scored</div>
          </div>

          {liveError ? <div className="mb-4 rounded-xl border border-red-400/20 bg-red-400/[0.05] p-3 text-sm text-red-100">{liveError}</div> : null}

          <div className="space-y-3">
            {scored.slice(0, 12).map((item) => <FeedCard key={item.investigation_id} item={item} onOpen={setSelected} />)}
            {scored.length === 0 ? <div className="rounded-2xl border border-dashed border-white/10 p-10 text-center text-sm text-white/30">Waiting for the next scored Telegram investigation…</div> : null}
          </div>
        </section>

        <section className="mt-10 rounded-3xl border border-white/10 bg-white/[0.02] p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">Classification stream</div>
              <div className="mt-1 text-xs text-white/30">Non-financial and unresolved messages stay visible here without cluttering the risk feed.</div>
            </div>
            <div className="text-xs text-white/30">{classified.length} records</div>
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-2">
            {classified.slice(0, 8).map((item) => (
              <button key={item.investigation_id} onClick={() => setSelected(item)} className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-left hover:bg-white/[0.04]">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold">{item.ticker || item.tickers?.[0] || "Market topic"}</div>
                  <span className={`rounded-full border px-2 py-1 text-[10px] ${statusTone(item.impact?.status || item.status)}`}>{human(item.impact?.status || item.status || "pending")}</span>
                </div>
                <div className="mt-2 text-xs text-white/35">{item.classification?.message_type || "—"} · {human(item.classification?.market_domain || item.classification?.domain)}</div>
              </button>
            ))}
          </div>
        </section>

        <section className="mt-8 grid gap-3 md:grid-cols-4">
          <SmallStat label="1. Classify" value="Stock / commodity / macro / sector / index" />
          <SmallStat label="2. Map impact" value="Resolve exact entity or topic" />
          <SmallStat label="3. Gather evidence" value="Market / news / Reddit / X / Instagram / StockTwits" />
          <SmallStat label="4. Aggregate risk" value="Explainable Dakota 0–100 score" />
        </section>

        <p className="mt-8 text-xs leading-5 text-white/25">Dakota reports risk indicators from available evidence. It does not determine fraud and does not provide buy/sell advice. Missing connectors remain visible as gaps.</p>
      </div>

      {selected ? <DetailPanel item={selected} onClose={() => setSelected(null)} /> : null}
    </main>
  );
}
