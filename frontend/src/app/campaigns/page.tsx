"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import { 
  Users, 
  Search, 
  Layers, 
  Radio, 
  ShieldAlert, 
  Sparkles, 
  Filter, 
  ExternalLink, 
  ChevronDown, 
  ChevronRight,
  Copy,
  Clock,
  AlertTriangle
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type TipItem = {
  investigation_id?: string;
  ticker?: string | null;
  timestamp?: string | null;
  fingerprint?: string | null;
  message_type?: string | null;
  urgency?: boolean;
  n_scam_markers?: number;
  price_target?: number | null;
  risk?: {
    score?: number;
    band?: string;
  } | null;
};

type ChannelCampaign = {
  channel_id: string;
  channel_name: string;
  channel_title?: string;
  channel_username?: string | null;
  platform: string;
  total_tips: number;
  entities_touched: string[];
  entities_count: number;
  first_seen?: string | null;
  last_seen?: string | null;
  distinct_text_count: number;
  copy_paste_count: number;
  copy_paste_percentage: number;
  distinct_ratio_str: string;
  scam_markers_total: number;
  urgency_tips_count: number;
  tips: TipItem[];
};

function formatTimeWindow(firstSeen?: string | null, lastSeen?: string | null) {
  if (!firstSeen || !lastSeen) return "Recent activity";
  const start = new Date(firstSeen);
  const end = new Date(lastSeen);
  if (isNaN(start.getTime()) || isNaN(end.getTime())) return "Recent activity";

  const diffMs = Math.abs(end.getTime() - start.getTime());
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  let spanStr = "";
  if (diffDays > 0) {
    spanStr = `${diffDays}d ${diffHours % 24}h span`;
  } else if (diffHours > 0) {
    spanStr = `${diffHours}h ${diffMins % 60}m span`;
  } else {
    spanStr = `${Math.max(1, diffMins)}m span`;
  }

  const startFormatted = start.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  const endFormatted = end.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  if (startFormatted === endFormatted) {
    return `${startFormatted} (burst)`;
  }
  return `${startFormatted} → ${endFormatted} (${spanStr})`;
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<ChannelCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedChannels, setExpandedChannels] = useState<Record<string, boolean>>({});
  const [activeEntityFilter, setActiveEntityFilter] = useState<string>("");
  const [searchTerm, setSearchTerm] = useState("");

  async function loadCampaigns() {
    try {
      // First try dedicated /api/campaigns endpoint
      const res = await fetch(`${API}/api/campaigns?limit=200`, { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        if (data.channels && Array.isArray(data.channels)) {
          setCampaigns(data.channels);
          // Auto-expand the #1 most active channel by default for 0-click insight
          if (data.channels.length > 0 && Object.keys(expandedChannels).length === 0) {
            setExpandedChannels({ [data.channels[0].channel_id]: true });
          }
          setLoading(false);
          return;
        }
      }

      // Fallback: derive directly from /api/investigations/live
      const liveRes = await fetch(`${API}/api/investigations/live?limit=200`, { cache: "no-store" });
      if (!liveRes.ok) throw new Error("Could not load live investigations feed");
      const liveData = await liveRes.json();
      const items = liveData.items || [];

      // Group by channel/actor
      const groups: Record<string, any[]> = {};
      for (const item of items) {
        const key =
          item.channel_username ||
          item.investigation?.source ||
          item.channel ||
          "unknown_channel";
        if (!groups[key]) groups[key] = [];
        groups[key].push(item);
      }

      const parsedChannels: ChannelCampaign[] = Object.entries(groups).map(([chKey, tips]) => {
        const entitiesSet = new Set<string>();
        tips.forEach((t) => {
          if (t.ticker) entitiesSet.add(t.ticker.toUpperCase());
          if (t.tickers) t.tickers.forEach((tk: string) => tk && entitiesSet.add(tk.toUpperCase()));
          if (t.impact?.entity) entitiesSet.add(t.impact.entity.toUpperCase());
        });
        const entities = Array.from(entitiesSet).sort();

        const tsList = tips
          .map((t) => t.telegram_timestamp || t.captured_at || t.stored_at)
          .filter(Boolean);
        const firstSeen = tsList.length ? tsList.reduce((a, b) => (a < b ? a : b)) : null;
        const lastSeen = tsList.length ? tsList.reduce((a, b) => (a > b ? a : b)) : null;

        const fps = tips.map((t) => t.fingerprint).filter(Boolean);
        const distinctFps = new Set(fps).size || tips.length;
        const copyPasteCount = Math.max(0, fps.length - distinctFps);
        const copyPastePct = tips.length ? Math.round((copyPasteCount / tips.length) * 100) : 0;

        return {
          channel_id: chKey,
          channel_name: chKey,
          channel_title: tips[0]?.channel || chKey,
          channel_username: tips[0]?.channel_username || (chKey.startsWith("@") ? chKey : null),
          platform: chKey.toLowerCase().includes("telegram") || chKey.startsWith("@") ? "telegram" : "intake",
          total_tips: tips.length,
          entities_touched: entities,
          entities_count: entities.length,
          first_seen: firstSeen,
          last_seen: lastSeen,
          distinct_text_count: distinctFps,
          copy_paste_count: copyPasteCount,
          copy_paste_percentage: copyPastePct,
          distinct_ratio_str: `${distinctFps} distinct / ${tips.length} tips`,
          scam_markers_total: tips.reduce((acc, t) => acc + (t.n_scam_markers || 0), 0),
          urgency_tips_count: tips.filter((t) => t.urgency).length,
          tips: tips.map((t) => ({
            investigation_id: t.investigation_id,
            ticker: t.ticker || t.tickers?.[0] || t.impact?.entity,
            timestamp: t.telegram_timestamp || t.captured_at || t.stored_at,
            fingerprint: t.fingerprint,
            message_type: t.classification?.message_type || t.classification?.type,
            urgency: Boolean(t.urgency),
            n_scam_markers: t.n_scam_markers || 0,
            risk: t.risk,
          })),
        };
      });

      parsedChannels.sort((a, b) => b.total_tips - a.total_tips);
      setCampaigns(parsedChannels);
      if (parsedChannels.length > 0 && Object.keys(expandedChannels).length === 0) {
        setExpandedChannels({ [parsedChannels[0].channel_id]: true });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load campaigns");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCampaigns();
    const interval = setInterval(loadCampaigns, 6000);
    return () => clearInterval(interval);
  }, []);

  function toggleExpand(channelId: string) {
    setExpandedChannels((prev) => ({
      ...prev,
      [channelId]: !prev[channelId],
    }));
  }

  // Filtered campaigns
  const filteredCampaigns = useMemo(() => {
    return campaigns.filter((c) => {
      const matchSearch =
        !searchTerm ||
        c.channel_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        c.channel_title?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        c.entities_touched.some((e) => e.toLowerCase().includes(searchTerm.toLowerCase()));

      const matchEntity =
        !activeEntityFilter || c.entities_touched.includes(activeEntityFilter.toUpperCase());

      return matchSearch && matchEntity;
    });
  }, [campaigns, searchTerm, activeEntityFilter]);

  // Aggregate metrics
  const totalTips = useMemo(() => campaigns.reduce((acc, c) => acc + c.total_tips, 0), [campaigns]);
  const mostActiveChannel = campaigns[0];
  const allUniqueEntities = useMemo(() => {
    const s = new Set<string>();
    campaigns.forEach((c) => c.entities_touched.forEach((e) => s.add(e)));
    return Array.from(s).sort();
  }, [campaigns]);

  return (
    <main className="min-h-screen bg-[#05070a] text-slate-100 flex flex-col bg-terminal-grid">
      <Navbar />

      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 sm:py-12 flex-1">
        <header className="mb-8">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/[0.08] pb-6">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-mono font-semibold text-cyan-300 mb-3">
                <Users className="h-3.5 w-3.5" />
                <span>COORDINATED SYNDICATE SURVEILLANCE</span>
              </div>
              <h1 className="text-3xl sm:text-4xl font-black text-white">
                Syndicate &amp; Channel Campaigns
              </h1>
              <p className="mt-2 max-w-2xl text-sm text-slate-400">
                Coordinated tip actors collapsed into single pattern cards. Detect which channel is flooding retail traders, which entities are being touched, and the distinct-text vs copy-paste ratio.
              </p>
            </div>

            <div className="flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-mono font-semibold text-emerald-300">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span>LIVE CLUSTER INTAKE</span>
            </div>
          </div>
        </header>

        {/* Answer Metric 2: "Which channel is most active?" - Top Insights Banner */}
        {!loading && campaigns.length > 0 && (
          <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Stat 1: Most Active Channel */}
            <div className="rounded-2xl border border-sky-500/30 bg-sky-950/20 p-5 shadow-[0_0_20px_rgba(14,165,233,0.1)]">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-sky-400">
                #1 Most Active Actor
              </div>
              <div className="mt-1.5 text-lg font-bold text-white truncate">
                {mostActiveChannel?.channel_username || mostActiveChannel?.channel_name}
              </div>
              <div className="mt-1 flex items-center gap-2 text-xs text-sky-300/80">
                <span className="font-semibold text-white">{mostActiveChannel?.total_tips} tips</span>
                <span>•</span>
                <span>{mostActiveChannel?.entities_count} entities touched</span>
              </div>
            </div>

            {/* Stat 2: Total Channels Monitored */}
            <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
                Actor Channels Detected
              </div>
              <div className="mt-1.5 text-2xl font-bold text-white">
                {campaigns.length} <span className="text-sm font-normal text-zinc-500">Channels</span>
              </div>
              <div className="mt-1 text-xs text-zinc-400">
                {totalTips} total tips aggregated into actor profiles
              </div>
            </div>

            {/* Stat 3: Entities Targeted */}
            <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
                Target Entities Touched
              </div>
              <div className="mt-1.5 text-2xl font-bold text-white">
                {allUniqueEntities.length} <span className="text-sm font-normal text-zinc-500">Securities</span>
              </div>
              <div className="mt-1 text-xs text-zinc-400 truncate">
                {allUniqueEntities.slice(0, 4).join(", ")}
                {allUniqueEntities.length > 4 ? ` +${allUniqueEntities.length - 4} more` : ""}
              </div>
            </div>

            {/* Stat 4: Pattern Insight */}
            <div className="rounded-2xl border border-amber-500/30 bg-amber-950/20 p-5">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-amber-400">
                Highest Duplicate Rate
              </div>
              <div className="mt-1.5 text-2xl font-bold text-amber-200">
                {Math.max(...campaigns.map((c) => c.copy_paste_percentage), 0)}%
              </div>
              <div className="mt-1 text-xs text-amber-300/70">
                Copy-paste message templates detected
              </div>
            </div>
          </div>
        )}

        {/* Filter & Search Bar */}
        <div className="mt-8 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
          <div className="relative flex-1 max-w-md">
            <span className="absolute inset-y-0 left-0 flex items-center pl-3.5 pointer-events-none text-zinc-400 text-sm">
              🔍
            </span>
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search by channel (@markemahakelpredictions) or ticker..."
              className="w-full rounded-xl border border-white/10 bg-zinc-900/90 pl-10 pr-10 py-2.5 text-sm text-white placeholder-zinc-500 outline-none transition focus:border-sky-500/50"
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm("")}
                className="absolute inset-y-0 right-0 flex items-center pr-3 text-zinc-400 hover:text-white text-xs"
              >
                ✕
              </button>
            )}
          </div>

          {/* Quick Entity Filter Chips */}
          {allUniqueEntities.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 overflow-x-auto pb-1 max-w-xl">
              <span className="text-xs text-zinc-500 mr-1">Filter entity:</span>
              <button
                onClick={() => setActiveEntityFilter("")}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                  activeEntityFilter === ""
                    ? "bg-sky-500/20 text-sky-300 border border-sky-400/40"
                    : "bg-white/[0.03] text-zinc-400 border border-white/5 hover:text-white"
                }`}
              >
                All ({allUniqueEntities.length})
              </button>
              {allUniqueEntities.slice(0, 8).map((entity) => (
                <button
                  key={entity}
                  onClick={() => setActiveEntityFilter(activeEntityFilter === entity ? "" : entity)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                    activeEntityFilter === entity
                      ? "bg-sky-500 text-black font-bold shadow-sm shadow-sky-500/30"
                      : "bg-white/[0.03] text-zinc-400 border border-white/5 hover:text-white hover:bg-white/[0.08]"
                  }`}
                >
                  {entity}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Content Section */}
        <div className="mt-8">
          {loading && (
            <div className="rounded-3xl border border-white/10 bg-white/[0.02] p-12 text-center">
              <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-sky-400 border-t-transparent mb-3" />
              <p className="text-sm text-zinc-400">Aggregating live tip streams into channel actor profiles...</p>
            </div>
          )}

          {error && !loading && (
            <div className="rounded-2xl border border-red-500/30 bg-red-950/20 p-6 text-sm text-red-300">
              {error}
            </div>
          )}

          {!loading && !error && filteredCampaigns.length === 0 && (
            <div className="rounded-3xl border border-white/10 bg-white/[0.02] p-12 text-center">
              <h2 className="text-xl font-bold text-white">No campaigns found</h2>
              <p className="mt-2 text-sm text-zinc-400">
                {searchTerm || activeEntityFilter
                  ? "No channel actors matched your search or entity filter."
                  : "Waiting for incoming Telegram tips or manual tip submissions to correlate."}
              </p>
              {(searchTerm || activeEntityFilter) && (
                <button
                  onClick={() => {
                    setSearchTerm("");
                    setActiveEntityFilter("");
                  }}
                  className="mt-4 rounded-xl bg-zinc-800 px-4 py-2 text-xs font-semibold text-white hover:bg-zinc-700"
                >
                  Clear Filters
                </button>
              )}
            </div>
          )}

          {/* Unified Channel Actor Campaign Cards */}
          <div className="space-y-6">
            {filteredCampaigns.map((camp, rankIdx) => {
              const isExpanded = Boolean(expandedChannels[camp.channel_id]);
              const isTopActor = rankIdx === 0;

              return (
                <div
                  key={camp.channel_id}
                  className={`rounded-3xl border transition-all ${
                    isTopActor
                      ? "border-sky-500/30 bg-gradient-to-b from-[#0b1424] via-[#070b14] to-[#04070c] shadow-[0_0_35px_rgba(14,165,233,0.12)]"
                      : "border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.03]"
                  }`}
                >
                  {/* Card Header Banner (Click to toggle expansion) */}
                  <div
                    onClick={() => toggleExpand(camp.channel_id)}
                    className="cursor-pointer p-6 sm:p-7 select-none"
                  >
                    <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
                      {/* Left: Channel Info & Entities Touched */}
                      <div className="space-y-3 min-w-0">
                        <div className="flex flex-wrap items-center gap-2.5">
                          {isTopActor && (
                            <span className="rounded-full bg-sky-500/20 border border-sky-400/40 px-2.5 py-0.5 text-[11px] font-bold text-sky-300 uppercase tracking-wide">
                              #1 Most Active Actor
                            </span>
                          )}
                          <span className="rounded-full bg-white/5 border border-white/10 px-2.5 py-0.5 text-[11px] font-semibold text-zinc-300 flex items-center gap-1.5">
                            <span className="text-sky-400">✈</span> Telegram Channel
                          </span>
                          <span className="text-xs text-zinc-500">
                            ID: <code className="font-mono text-zinc-400">{camp.channel_id}</code>
                          </span>
                        </div>

                        {/* Channel Title */}
                        <div>
                          <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white flex items-center gap-2">
                            <span>{camp.channel_username || camp.channel_title || camp.channel_name}</span>
                          </h2>
                          {camp.channel_title && camp.channel_username && (
                            <p className="mt-0.5 text-xs text-zinc-400">
                              Channel Title: <span className="text-zinc-300 font-medium">{camp.channel_title}</span>
                            </p>
                          )}
                        </div>

                        {/* Entities Touched Badges */}
                        <div>
                          <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-1.5 flex items-center gap-2">
                            <span>Entities Touched</span>
                            <span className="text-zinc-500">({camp.entities_count} securities targetted)</span>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {camp.entities_touched.length === 0 ? (
                              <span className="text-xs text-zinc-500 italic">No specific tickers extracted</span>
                            ) : (
                              camp.entities_touched.map((ent) => (
                                <Link
                                  key={ent}
                                  href={`/stocks/${ent}`}
                                  onClick={(e) => e.stopPropagation()}
                                  className="inline-flex items-center gap-1 rounded-lg border border-sky-400/20 bg-sky-400/10 px-2.5 py-1 text-xs font-bold text-sky-200 transition hover:bg-sky-400 hover:text-black"
                                >
                                  <span>{ent}</span>
                                  <span className="text-[10px] opacity-60">↗</span>
                                </Link>
                              ))
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Right: Metrics & Distinct-Text vs Copy-Paste Ratio */}
                      <div className="flex flex-col sm:flex-row lg:flex-col items-start lg:items-end justify-between gap-4 lg:min-w-[280px]">
                        {/* Tip Count Badge */}
                        <div className="lg:text-right">
                          <div className="text-3xl sm:text-4xl font-black text-sky-400">
                            {camp.total_tips}
                            <span className="text-sm font-normal text-zinc-500 ml-1.5">tips</span>
                          </div>
                          <div className="text-xs text-zinc-400 mt-0.5">
                            First seen → Last seen window
                          </div>
                          <div className="text-[11px] text-zinc-300 font-mono mt-0.5">
                            {formatTimeWindow(camp.first_seen, camp.last_seen)}
                          </div>
                        </div>

                        {/* Distinct-Text vs Copy-Paste Ratio */}
                        <div className="w-full sm:w-auto lg:w-full rounded-2xl border border-white/10 bg-black/40 p-3.5 lg:text-right">
                          <div className="flex items-center justify-between lg:justify-end gap-2 text-xs font-semibold">
                            <span className="text-zinc-400">Distinct vs Copy-Paste:</span>
                            <span className="text-white font-mono">{camp.distinct_ratio_str}</span>
                          </div>

                          {/* Visual Ratio Progress Bar */}
                          <div className="mt-2 h-2 w-full rounded-full bg-zinc-800 overflow-hidden flex">
                            <div
                              style={{ width: `${100 - camp.copy_paste_percentage}%` }}
                              className="h-full bg-emerald-400"
                              title={`${camp.distinct_text_count} Distinct Texts`}
                            />
                            <div
                              style={{ width: `${camp.copy_paste_percentage}%` }}
                              className="h-full bg-amber-400"
                              title={`${camp.copy_paste_count} Copy-Paste Duplicates`}
                            />
                          </div>

                          <div className="mt-1.5 flex items-center justify-between text-[10px] text-zinc-400">
                            <span className="flex items-center gap-1">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                              <span>{100 - camp.copy_paste_percentage}% Unique</span>
                            </span>
                            <span className="flex items-center gap-1 font-semibold text-amber-300">
                              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                              <span>{camp.copy_paste_percentage}% Copy-Paste</span>
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Bottom Action Footer of Card Header */}
                    <div className="mt-5 pt-4 border-t border-white/10 flex items-center justify-between text-xs text-zinc-400">
                      <div className="flex items-center gap-4">
                        {camp.urgency_tips_count > 0 && (
                          <span className="flex items-center gap-1 text-amber-400">
                            <span>⚡</span> {camp.urgency_tips_count} urgency pushes
                          </span>
                        )}
                        {camp.scam_markers_total > 0 && (
                          <span className="flex items-center gap-1 text-red-400">
                            <span>⚠</span> {camp.scam_markers_total} scam markers
                          </span>
                        )}
                      </div>

                      {/* Expand / Collapse Indicator (Answers Metric 1: 1 click to reach specific tip) */}
                      <div className="flex items-center gap-1.5 font-semibold text-sky-400 hover:text-sky-300">
                        <span>{isExpanded ? "Hide individual tips" : `Expand all ${camp.total_tips} tips`}</span>
                        <span className="text-sm">{isExpanded ? "▲" : "▼"}</span>
                      </div>
                    </div>
                  </div>

                  {/* Expanded Individual Tips Drawer */}
                  {isExpanded && (
                    <div className="border-t border-white/10 bg-black/50 p-6 sm:p-7 rounded-b-3xl space-y-3 animate-fadeIn">
                      <div className="flex items-center justify-between mb-4">
                        <div className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                          Individual Tip Log ({camp.tips.length} messages)
                        </div>
                        <div className="text-xs text-zinc-500">
                          Click any tip to inspect full evidence trail
                        </div>
                      </div>

                      <div className="space-y-2.5 max-h-[500px] overflow-y-auto pr-1">
                        {camp.tips.map((tip, tipIdx) => (
                          <div
                            key={tip.investigation_id || tipIdx}
                            className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5 hover:bg-white/[0.04] transition flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
                          >
                            <div className="flex items-center gap-3">
                              {/* Ticker / Entity */}
                              {tip.ticker ? (
                                <Link
                                  href={`/stocks/${tip.ticker}`}
                                  className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-2.5 py-1 font-bold text-sky-300 hover:bg-sky-400 hover:text-black transition"
                                >
                                  {tip.ticker}
                                </Link>
                              ) : (
                                <span className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 font-medium text-zinc-400">
                                  General Market
                                </span>
                              )}

                              {/* Message Type */}
                              <span className="text-zinc-300 font-medium">
                                {tip.message_type || "Market Trading Tip"}
                              </span>

                              {/* Urgency Badge */}
                              {tip.urgency && (
                                <span className="rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 px-1.5 py-0.5 text-[10px] font-bold">
                                  URGENT
                                </span>
                              )}

                              {/* Scam Markers */}
                              {(tip.n_scam_markers ?? 0) > 0 && (
                                <span className="rounded bg-red-500/20 text-red-300 border border-red-500/30 px-1.5 py-0.5 text-[10px] font-bold">
                                  {tip.n_scam_markers} markers
                                </span>
                              )}
                            </div>

                            {/* Right: Timestamp & Fingerprint */}
                            <div className="flex items-center gap-3 text-zinc-400 text-[11px] sm:text-right">
                              {tip.fingerprint && (
                                <span className="font-mono bg-black/40 px-2 py-0.5 rounded text-[10px] text-zinc-400">
                                  fp: {tip.fingerprint.slice(0, 10)}...
                                </span>
                              )}
                              <span>
                                {tip.timestamp ? new Date(tip.timestamp).toLocaleString() : "Recent"}
                              </span>

                              {tip.investigation_id && (
                                <Link
                                  href={`/investigate`}
                                  className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-sky-500 hover:text-black transition"
                                >
                                  Inspect →
                                </Link>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer info */}
        <footer className="mt-16 border-t border-white/10 pt-6 text-xs text-zinc-500 flex flex-wrap items-center justify-between gap-4">
          <div>Dakota Intelligence • Coordinated Campaign Actor Detection</div>
          <div className="flex gap-4">
            <Link href="/" className="hover:text-white transition">Home Tip Check</Link>
            <Link href="/stocks" className="hover:text-white transition">Indian Equities</Link>
            <Link href="/investigate" className="hover:text-white transition">Live Stream</Link>
          </div>
        </footer>
      </div>
    </main>
  );
}