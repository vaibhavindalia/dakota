"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Observation = { signal: string; severity: string; text: string };
type Risk = {
  score: number;
  band: string;
  raw_score?: number;
  available_score_points?: number;
  components?: Record<string, number>;
  reasons?: string[];
  method?: string;
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
  };
  risk?: Risk | null;
  status?: string;
  disclaimer?: string;
};

type ManualResult = any;

function bandClass(band?: string) {
  const b = (band || "").toLowerCase();
  if (b.includes("high")) return "border-red-400/30 bg-red-400/10 text-red-200";
  if (b.includes("elev")) return "border-amber-400/30 bg-amber-400/10 text-amber-200";
  return "border-emerald-400/20 bg-emerald-400/10 text-emerald-200";
}

function fmt(v: unknown, digits = 1) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function title(v?: string | null) {
  return (v || "—").replaceAll("_", " ");
}

function timeAgo(value?: string | null) {
  if (!value) return "unknown time";
  const ms = Date.now() - new Date(value).getTime();
  const mins = Math.max(0, Math.floor(ms / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function RiskBadge({ risk }: { risk?: Risk | null }) {
  if (!risk) return <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-white/40">No score yet</span>;
  return <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${bandClass(risk.band)}`}>{fmt(risk.score)} · {risk.band}</span>;
}

function EvidenceCard({ label, value, tone = "default" }: { label: string; value: string; tone?: string }) {
  const cls = tone === "live"
    ? "border-emerald-400/20 bg-emerald-400/[0.05]"
    : "border-white/10 bg-white/[0.03]";
  return (
    <div className={`rounded-xl border p-4 ${cls}`}>
      <div className="text-[10px] uppercase tracking-[0.22em] text-white/35">{label}</div>
      <div className="mt-2 text-sm font-semibold text-white">{value}</div>
    </div>
  );
}

function LiveCard({ item, onOpen }: { item: LiveItem; onOpen: (id: string) => void }) {
  const risk = item.risk || item.investigation?.risk;
  const cls = item.classification;
  const impact = item.impact;
  const target = impact?.entity || item.ticker || item.tickers?.[0] || "Market topic";

  return (
    <button onClick={() => onOpen(item.investigation_id)} className="w-full text-left rounded-2xl border border-white/10 bg-white/[0.03] p-5 transition hover:border-sky-400/25 hover:bg-white/[0.045]">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold text-white">{title(target)}</span>
            <RiskBadge risk={risk} />
          </div>
          <div className="mt-1 text-xs text-white/35">{item.channel_username || item.channel || "Telegram"} · {timeAgo(item.telegram_timestamp || item.captured_at)}</div>
        </div>
        <div className="text-right text-xs text-white/35">#{item.message_id ?? "—"}</div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <EvidenceCard label="Message type" value={cls?.message_type || "—"} />
        <EvidenceCard label="Domain" value={title(cls?.market_domain || cls?.domain)} />
        <EvidenceCard label="Impact" value={title(impact?.exact_topic || impact?.entity)} />
        <EvidenceCard label="Status" value={title(item.status || impact?.status)} tone="live" />
      </div>

      {impact?.potentially_affected_areas?.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {impact.potentially_affected_areas.slice(0, 6).map((area) => (
            <span key={area} className="rounded-full border border-white/10 px-2.5 py-1 text-[11px] text-white/50">{title(area)}</span>
          ))}
        </div>
      ) : null}

      {risk?.reasons?.length ? (
        <div className="mt-4 space-y-2">
          {risk.reasons.slice(0, 3).map((reason) => <div key={reason} className="rounded-lg bg-black/10 p-3 text-xs text-white/60">{reason}</div>)}
        </div>
      ) : null}
    </button>
  );
}

function DetailPanel({ item, onClose }: { item: LiveItem; onClose: () => void }) {
  const result = item.investigation || {};
  const risk = item.risk || result.risk;
  return (
    <div className="fixed inset-0 z-50 bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="mx-auto mt-8 max-h-[88vh] max-w-5xl overflow-y-auto rounded-3xl border border-white/10 bg-[#0b101a] p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.25em] text-sky-400">Investigation detail</div>
            <h2 className="mt-2 text-3xl font-bold">{title(item.impact?.entity || item.ticker || "Market topic")}</h2>
            <p className="mt-1 text-sm text-white/40">{item.channel_username || item.channel} · {item.investigation_id}</p>
          </div>
          <button onClick={onClose} className="rounded-lg border border-white/10 px-3 py-2 text-sm text-white/60 hover:text-white">Close</button>
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <EvidenceCard label="Classification" value={item.classification?.message_type || "—"} />
          <EvidenceCard label="Domain" value={title(item.classification?.market_domain || item.classification?.domain)} />
          <EvidenceCard label="Exact topic" value={title(item.impact?.exact_topic || item.impact?.entity)} />
          <EvidenceCard label="Confidence" value={item.classification?.confidence == null ? "—" : `${fmt(item.classification.confidence * 100)}%`} />
        </div>

        <div className={`mt-6 rounded-2xl border p-5 ${bandClass(risk?.band)}`}>
          <div className="text-xs uppercase tracking-[0.2em] opacity-70">Risk aggregation</div>
          <div className="mt-2 flex items-end gap-3"><span className="text-5xl font-bold">{risk ? fmt(risk.score) : "—"}</span><span className="mb-2 text-sm">/100 · {risk?.band || "pending"}</span></div>
          <div className="mt-3 text-xs opacity-60">{risk?.method || "Waiting for evidence aggregation."}</div>
        </div>

        {risk?.components ? (
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(risk.components).map(([key, value]) => <EvidenceCard key={key} label={title(key)} value={String(value)} />)}
          </div>
        ) : null}

        {risk?.reasons?.length ? (
          <div className="mt-6">
            <div className="mb-3 text-sm font-semibold">Why Dakota raised the score</div>
            <div className="grid gap-2 md:grid-cols-2">{risk.reasons.map((r) => <div key={r} className="rounded-xl border border-white/10 p-3 text-sm text-white/65">{r}</div>)}</div>
          </div>
        ) : null}

        {result.evidence?.news ? (
          <div className="mt-6 rounded-2xl border border-white/10 p-5">
            <div className="flex items-center justify-between"><div className="text-sm font-semibold">News evidence</div><div className="text-xs uppercase tracking-widest text-white/35">{result.evidence.news.status}</div></div>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <EvidenceCard label="Articles" value={String(result.evidence.news.article_count ?? 0)} />
              <EvidenceCard label="Hype hits" value={String(result.evidence.news.hype_article_count ?? 0)} />
              <EvidenceCard label="Red flags" value={String(result.evidence.news.red_flag_article_count ?? 0)} />
            </div>
            <div className="mt-4 space-y-2">{(result.evidence.news.articles || []).slice(0, 8).map((a: any) => <a key={a.url} href={a.url} target="_blank" rel="noreferrer" className="block rounded-xl border border-white/10 p-3 hover:bg-white/[0.03]"><div className="text-sm text-white/80">{a.title || "Untitled"}</div><div className="mt-1 text-xs text-white/35">{a.domain || "source"}</div></a>)}</div>
          </div>
        ) : null}

        {result.evidence?.social ? (
          <div className="mt-6 rounded-2xl border border-white/10 p-5">
            <div className="text-sm font-semibold">Social evidence coverage</div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(result.evidence.social).map(([key, value]: any) => <EvidenceCard key={key} label={key} value={String(value?.status || "unknown")} />)}
            </div>
          </div>
        ) : null}

        {item.impact?.rationale ? <div className="mt-6 rounded-xl border border-sky-400/15 bg-sky-400/[0.04] p-4 text-sm text-white/65">{item.impact.rationale}</div> : null}
        {item.disclaimer && <div className="mt-6 text-xs leading-5 text-white/30">{item.disclaimer}</div>}
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

  const headline = useMemo(() => live[0], [live]);

  return (
    <main className="min-h-screen bg-[#080b12] px-6 py-10 text-white">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.28em] text-sky-400">Dakota Investigation Engine</div>
            <h1 className="mt-2 text-4xl font-bold tracking-tight">Every tip gets an investigation.</h1>
            <p className="mt-3 max-w-3xl text-white/50">Telegram intake → classification → exact impact → evidence collection → explainable risk aggregation. Missing connectors are shown as gaps, never silently treated as clean.</p>
          </div>
          <div className="rounded-full border border-emerald-400/20 bg-emerald-400/[0.06] px-4 py-2 text-xs font-semibold text-emerald-200">● LIVE TELEGRAM FEED</div>
        </div>

        <section className="rounded-2xl border border-sky-400/15 bg-sky-400/[0.03] p-5">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div><div className="text-sm font-semibold">Latest incoming investigation</div><div className="mt-1 text-xs text-white/35">The dashboard refreshes automatically every 3 seconds.</div></div>
            {headline ? <RiskBadge risk={headline.risk || headline.investigation?.risk} /> : <span className="text-xs text-white/35">Waiting for the next Telegram post…</span>}
          </div>
        </section>

        <section className="mt-8 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <div className="mb-4 text-sm font-semibold">Manual investigation</div>
          <form onSubmit={submit} className="flex flex-col gap-4 lg:flex-row">
            <textarea value={tip} onChange={(e) => setTip(e.target.value)} required rows={5} placeholder="Paste any Telegram / WhatsApp / X / Reddit tip here…" className="min-h-32 flex-1 resize-y rounded-xl border border-white/10 bg-black/20 p-4 text-sm outline-none placeholder:text-white/25 focus:border-sky-400/40" />
            <div className="w-full lg:w-60">
              <label className="text-xs uppercase tracking-widest text-white/35">Source</label>
              <select value={source} onChange={(e) => setSource(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-[#101521] px-3 py-3 text-sm"><option value="manual">Manual</option><option value="telegram">Telegram</option><option value="whatsapp">WhatsApp</option><option value="x">X</option><option value="reddit">Reddit</option><option value="instagram">Instagram</option></select>
              <button disabled={loading} className="mt-4 w-full rounded-xl bg-sky-500 px-4 py-3 font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50">{loading ? "Investigating…" : "Investigate"}</button>
            </div>
          </form>
          {manualError && <div className="mt-4 rounded-xl border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">{manualError}</div>}
        </section>

        {manual && (
          <section className="mt-8 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <div className="text-sm font-semibold">Manual result</div>
            <pre className="mt-4 max-h-96 overflow-auto rounded-xl bg-black/30 p-4 text-xs text-white/65">{JSON.stringify(manual, null, 2)}</pre>
          </section>
        )}

        <section className="mt-10">
          <div className="mb-4 flex items-end justify-between"><div><div className="text-sm font-semibold">Live investigations</div><div className="mt-1 text-xs text-white/35">Derived records only — original Telegram message text is not stored.</div></div><div className="text-xs text-white/35">{live.length} records</div></div>
          {liveError && <div className="mb-4 rounded-xl border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">{liveError}</div>}
          <div className="space-y-3">
            {live.length === 0 ? <div className="rounded-2xl border border-dashed border-white/10 p-10 text-center text-sm text-white/35">Waiting for Telegram investigations…</div> : live.map((item) => <LiveCard key={item.investigation_id} item={item} onOpen={(id) => setSelected(live.find((x) => x.investigation_id === id) || null)} />)}
          </div>
        </section>

        <div className="mt-8 grid gap-3 md:grid-cols-4">
          <EvidenceCard label="1. Classify" value="Stock / commodity / macro / sector / index" />
          <EvidenceCard label="2. Map impact" value="Resolve exact entity/topic" />
          <EvidenceCard label="3. Gather evidence" value="Market / news / social / company" />
          <EvidenceCard label="4. Aggregate risk" value="Explainable 0–100 prototype" />
        </div>

        <p className="mt-8 text-xs leading-5 text-white/30">Dakota reports risk indicators from available evidence. It does not determine fraud and does not provide buy/sell advice. Public Telegram monitoring uses authorized account access and an explicit channel allowlist.</p>
      </div>
      {selected && <DetailPanel item={selected} onClose={() => setSelected(null)} />}
    </main>
  );
}
