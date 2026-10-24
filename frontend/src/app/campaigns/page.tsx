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
  AlertTriangle,
  RefreshCw,
  CheckCircle2,
  Eye,
  FileText,
  TrendingUp,
  Link2,
  XCircle,
  MessageSquare,
  AlertOctagon,
  Activity,
  Download
} from "lucide-react";
import CampaignGraph from "@/components/CampaignGraph";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type CampaignEvent = {
  event_id: string;
  campaign_id: string;
  event_type: string;
  ticker: string;
  source_label: string;
  event_timestamp: string;
  retrieved_at: string;
  data_freshness: string;
  summary: string;
  metadata?: Record<string, any>;
};

type CampaignRecord = {
  campaign_id: string;
  name: string;
  status: "active" | "monitoring" | "resolved" | "dismissed";
  tier: "HIGH" | "MODERATE" | "CANDIDATE";
  confidence_score: number;
  securities: string[];
  actors: string[];
  relationship_types: string[];
  relationship_explanations: Record<string, string>;
  evidence_ids: string[];
  alert_ids: string[];
  shared_urls: string[];
  shared_fingerprints: string[];
  time_window_hours: number;
  first_seen?: string | null;
  last_seen?: string | null;
  created_at: string;
  updated_at: string;
  notes?: string;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  dismissed_at?: string | null;
  contradictions?: string[];
  events?: CampaignEvent[];
};

type CampaignSummary = {
  total_campaigns: number;
  active_count: number;
  monitoring_count: number;
  resolved_count: number;
  dismissed_count: number;
  high_tier_count: number;
  moderate_tier_count: number;
  candidate_tier_count: number;
  total_securities_involved: number;
  total_actors_tracked: number;
  last_updated?: string | null;
};

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
  const [activeTab, setActiveTab] = useState<"syndicates" | "channels">("syndicates");
  const [campaigns, setCampaigns] = useState<CampaignRecord[]>([]);
  const [summary, setSummary] = useState<CampaignSummary | null>(null);
  const [channels, setChannels] = useState<ChannelCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRebuilding, setIsRebuilding] = useState(false);
  const [error, setError] = useState("");
  
  // Filtering
  const [searchTerm, setSearchTerm] = useState("");
  const [tierFilter, setTierFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [activeEntityFilter, setActiveEntityFilter] = useState<string>("");

  // Detailed modal / drawer
  const [selectedCampaign, setSelectedCampaign] = useState<CampaignRecord | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [newNote, setNewNote] = useState("");
  const [savingNote, setSavingNote] = useState(false);

  // Expanded legacy channel cards
  const [expandedChannels, setExpandedChannels] = useState<Record<string, boolean>>({});

  async function loadCampaignsData() {
    try {
      const res = await fetch(`${API}/api/campaigns?limit=100`, { cache: "no-store" });
      if (!res.ok) throw new Error("Could not load campaigns");
      const data = await res.json();
      
      if (data.campaigns && Array.isArray(data.campaigns)) {
        setCampaigns(data.campaigns);
      }
      if (data.summary) {
        setSummary(data.summary);
      }
      if (data.channels && Array.isArray(data.channels)) {
        setChannels(data.channels);
        if (data.channels.length > 0 && Object.keys(expandedChannels).length === 0) {
          setExpandedChannels({ [data.channels[0].channel_id]: true });
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load campaigns");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCampaignsData();
    const interval = setInterval(loadCampaignsData, 6000);
    return () => clearInterval(interval);
  }, []);

  async function handleRebuild() {
    setIsRebuilding(true);
    try {
      const res = await fetch(`${API}/api/campaigns/rebuild`, { method: "POST" });
      if (res.ok) {
        await loadCampaignsData();
      }
    } catch (err) {
      console.error("Rebuild error:", err);
    } finally {
      setIsRebuilding(false);
    }
  }

  async function handleCampaignAction(campaignId: string, action: "acknowledge" | "dismiss" | "monitor" | "resolve") {
    try {
      const res = await fetch(`${API}/api/campaigns/${campaignId}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: `Action ${action} triggered from dashboard` }),
      });
      if (res.ok) {
        await loadCampaignsData();
        if (selectedCampaign && selectedCampaign.campaign_id === campaignId) {
          openDetailModal(campaignId);
        }
      }
    } catch (err) {
      console.error(`Failed to ${action} campaign:`, err);
    }
  }

  async function openDetailModal(campaignId: string) {
    setLoadingDetail(true);
    try {
      const res = await fetch(`${API}/api/campaigns/${campaignId}`);
      if (res.ok) {
        const fullData = await res.json();
        setSelectedCampaign(fullData);
      }
    } catch (err) {
      console.error("Failed loading campaign detail:", err);
    } finally {
      setLoadingDetail(false);
    }
  }

  async function handleAddNote() {
    if (!selectedCampaign || !newNote.trim()) return;
    setSavingNote(true);
    try {
      const res = await fetch(`${API}/api/campaigns/${selectedCampaign.campaign_id}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: newNote }),
      });
      if (res.ok) {
        setNewNote("");
        await openDetailModal(selectedCampaign.campaign_id);
        await loadCampaignsData();
      }
    } catch (err) {
      console.error("Failed adding note:", err);
    } finally {
      setSavingNote(false);
    }
  }

  // Filtered campaigns
  const filteredCampaigns = useMemo(() => {
    return campaigns.filter((c) => {
      const matchSearch =
        !searchTerm ||
        c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        c.actors.some((a) => a.toLowerCase().includes(searchTerm.toLowerCase())) ||
        c.securities.some((s) => s.toLowerCase().includes(searchTerm.toLowerCase()));

      const matchTier = tierFilter === "ALL" || c.tier === tierFilter;
      const matchStatus = statusFilter === "ALL" || c.status === statusFilter;
      const matchEntity = !activeEntityFilter || c.securities.includes(activeEntityFilter.toUpperCase());

      return matchSearch && matchTier && matchStatus && matchEntity;
    });
  }, [campaigns, searchTerm, tierFilter, statusFilter, activeEntityFilter]);

  // Unique entities across all campaigns
  const allUniqueEntities = useMemo(() => {
    const s = new Set<string>();
    campaigns.forEach((c) => c.securities.forEach((tk) => s.add(tk)));
    return Array.from(s).sort();
  }, [campaigns]);

  return (
    <main className="min-h-screen bg-[#05070a] text-slate-100 flex flex-col bg-terminal-grid">
      <Navbar />

      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 sm:py-10 flex-1">
        {/* Header */}
        <header className="mb-6">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/[0.08] pb-6">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-mono font-semibold text-cyan-300 mb-3">
                <Users className="h-3.5 w-3.5" />
                <span>CROSS-SCRIP SYNDICATE CORRELATION &amp; FORENSIC CAMPAIGNS</span>
              </div>
              <h1 className="text-3xl sm:text-4xl font-black text-white tracking-tight">
                Forensic Campaigns Workspace
              </h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-400">
                Detects, correlates, and tracks multi-scrip promotional syndicates across public actors, repeated copy templates, shared URLs, and corroborating exchange alerts.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={handleRebuild}
                disabled={isRebuilding}
                className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-950/40 hover:bg-cyan-900/50 px-3.5 py-2 text-xs font-mono text-cyan-300 transition-colors shadow-sm disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isRebuilding ? "animate-spin text-cyan-400" : ""}`} />
                <span>{isRebuilding ? "Scanning Evidence..." : "Rebuild Correlation Scan"}</span>
              </button>
            </div>
          </div>
        </header>

        {/* Operational Overview Metric Cards */}
        {summary && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
            <div className="rounded-xl border border-white/[0.08] bg-slate-900/60 p-3.5">
              <div className="text-[11px] font-mono uppercase text-slate-400">Total Campaigns</div>
              <div className="text-2xl font-bold font-mono text-white mt-1">{summary.total_campaigns}</div>
              <div className="text-[10px] text-slate-400 mt-1">Cross-scrip entities</div>
            </div>

            <div className="rounded-xl border border-emerald-500/20 bg-emerald-950/20 p-3.5">
              <div className="text-[11px] font-mono uppercase text-emerald-400">Active Syndicates</div>
              <div className="text-2xl font-bold font-mono text-emerald-300 mt-1">{summary.active_count}</div>
              <div className="text-[10px] text-emerald-400/70 mt-1">Under investigation</div>
            </div>

            <div className="rounded-xl border border-rose-500/20 bg-rose-950/20 p-3.5">
              <div className="text-[11px] font-mono uppercase text-rose-400">High Confidence</div>
              <div className="text-2xl font-bold font-mono text-rose-300 mt-1">{summary.high_tier_count}</div>
              <div className="text-[10px] text-rose-400/70 mt-1">Multi-signal corroboration</div>
            </div>

            <div className="rounded-xl border border-cyan-500/20 bg-cyan-950/20 p-3.5">
              <div className="text-[11px] font-mono uppercase text-cyan-400">Securities Touched</div>
              <div className="text-2xl font-bold font-mono text-cyan-300 mt-1">{summary.total_securities_involved}</div>
              <div className="text-[10px] text-cyan-400/70 mt-1">NSE/BSE scrips</div>
            </div>

            <div className="rounded-xl border border-amber-500/20 bg-amber-950/20 p-3.5">
              <div className="text-[11px] font-mono uppercase text-amber-400">Promoter Actors</div>
              <div className="text-2xl font-bold font-mono text-amber-300 mt-1">{summary.total_actors_tracked}</div>
              <div className="text-[10px] text-amber-400/70 mt-1">Channels &amp; accounts</div>
            </div>

            <div className="rounded-xl border border-white/[0.08] bg-slate-900/60 p-3.5">
              <div className="text-[11px] font-mono uppercase text-slate-400">Monitoring / Resolved</div>
              <div className="text-2xl font-bold font-mono text-slate-200 mt-1">
                {summary.monitoring_count} / {summary.resolved_count}
              </div>
              <div className="text-[10px] text-slate-400 mt-1">Tracking lifecycle</div>
            </div>
          </div>
        )}

        {/* Tab Selection */}
        <div className="flex items-center gap-2 border-b border-white/[0.08] mb-6">
          <button
            onClick={() => setActiveTab("syndicates")}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-mono font-medium border-b-2 transition-colors ${
              activeTab === "syndicates"
                ? "border-cyan-400 text-cyan-300 bg-cyan-500/5"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <ShieldAlert className="h-4 w-4" />
            <span>Syndicate Campaigns ({campaigns.length})</span>
          </button>

          <button
            onClick={() => setActiveTab("channels")}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-mono font-medium border-b-2 transition-colors ${
              activeTab === "channels"
                ? "border-cyan-400 text-cyan-300 bg-cyan-500/5"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Layers className="h-4 w-4" />
            <span>Channel Fingerprint Clusters ({channels.length})</span>
          </button>
        </div>

        {/* TAB 1: SYNDICATE CAMPAIGNS */}
        {activeTab === "syndicates" && (
          <div>
            {/* Filter Toolbar */}
            <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between mb-6">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  type="text"
                  placeholder="Filter by scrip symbol, promoter handle, campaign name..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 rounded-lg bg-slate-900/80 border border-white/[0.08] text-xs font-mono text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500/50"
                />
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={tierFilter}
                  onChange={(e) => setTierFilter(e.target.value)}
                  className="rounded-lg bg-slate-900 border border-white/[0.08] px-3 py-2 text-xs font-mono text-slate-300 focus:outline-none focus:border-cyan-500/50"
                >
                  <option value="ALL">All Tiers</option>
                  <option value="HIGH">HIGH Confidence</option>
                  <option value="MODERATE">MODERATE Confidence</option>
                  <option value="CANDIDATE">CANDIDATE</option>
                </select>

                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="rounded-lg bg-slate-900 border border-white/[0.08] px-3 py-2 text-xs font-mono text-slate-300 focus:outline-none focus:border-cyan-500/50"
                >
                  <option value="ALL">All Statuses</option>
                  <option value="active">Active</option>
                  <option value="monitoring">Monitoring</option>
                  <option value="resolved">Resolved</option>
                  <option value="dismissed">Dismissed</option>
                </select>

                {allUniqueEntities.length > 0 && (
                  <select
                    value={activeEntityFilter}
                    onChange={(e) => setActiveEntityFilter(e.target.value)}
                    className="rounded-lg bg-slate-900 border border-white/[0.08] px-3 py-2 text-xs font-mono text-slate-300 focus:outline-none focus:border-cyan-500/50"
                  >
                    <option value="">All Tickers</option>
                    {allUniqueEntities.map((tk) => (
                      <option key={tk} value={tk}>{tk}</option>
                    ))}
                  </select>
                )}
              </div>
            </div>

            {/* Campaign Cards List */}
            {loading ? (
              <div className="py-16 text-center text-slate-500 font-mono text-xs">
                <RefreshCw className="h-6 w-6 animate-spin mx-auto text-cyan-400 mb-2" />
                Loading cross-scrip campaign records...
              </div>
            ) : filteredCampaigns.length === 0 ? (
              <div className="rounded-2xl border border-white/[0.08] bg-slate-900/30 p-12 text-center">
                <ShieldAlert className="h-10 w-10 text-slate-600 mx-auto mb-3" />
                <h3 className="text-base font-bold text-slate-300">No matching syndicate campaigns</h3>
                <p className="text-xs text-slate-500 max-w-md mx-auto mt-1">
                  No multi-scrip correlation records match your filters. Click &quot;Rebuild Correlation Scan&quot; to re-analyze historical investigations and alerts.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {filteredCampaigns.map((camp) => {
                  const isHigh = camp.tier === "HIGH";
                  const isMod = camp.tier === "MODERATE";

                  return (
                    <div
                      key={camp.campaign_id}
                      className={`rounded-2xl border transition-all p-5 ${
                        isHigh
                          ? "border-rose-500/30 bg-rose-950/[0.08] hover:border-rose-500/50"
                          : isMod
                          ? "border-amber-500/30 bg-amber-950/[0.08] hover:border-amber-500/50"
                          : "border-white/[0.08] bg-slate-900/40 hover:border-cyan-500/30"
                      }`}
                    >
                      <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
                        {/* Top Left: Campaign Header */}
                        <div className="flex-1">
                          <div className="flex flex-wrap items-center gap-2 mb-2">
                            <span
                              className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider ${
                                isHigh
                                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                  : isMod
                                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                                  : "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                              }`}
                            >
                              <span className={`h-1.5 w-1.5 rounded-full ${isHigh ? "bg-rose-400 animate-pulse" : isMod ? "bg-amber-400" : "bg-cyan-400"}`} />
                              {camp.tier} CONFIDENCE
                            </span>

                            <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold uppercase bg-slate-800 text-slate-300 border border-white/[0.08]">
                              STATUS: {camp.status}
                            </span>

                            <span className="text-xs font-mono text-slate-400">
                              Score: <strong className="text-white">{(camp.confidence_score * 100).toFixed(0)}%</strong>
                            </span>

                            <span className="text-xs font-mono text-slate-500">
                              ID: {camp.campaign_id}
                            </span>
                          </div>

                          <h2 className="text-lg font-bold text-white flex items-center gap-2">
                            {camp.name}
                          </h2>

                          <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mt-1">
                            <Clock className="h-3.5 w-3.5 text-slate-500" />
                            <span>{formatTimeWindow(camp.first_seen, camp.last_seen)}</span>
                            <span>•</span>
                            <span>Window: {camp.time_window_hours}h</span>
                          </div>

                          {/* Participating Securities Pills */}
                          <div className="mt-3 flex flex-wrap items-center gap-2">
                            <span className="text-xs font-mono text-slate-400 mr-1">Securities:</span>
                            {camp.securities.map((tk) => (
                              <Link
                                key={tk}
                                href={`/stocks/${tk}`}
                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800/80 hover:bg-cyan-950/60 border border-white/[0.08] hover:border-cyan-500/40 text-xs font-mono font-bold text-cyan-300 transition-colors"
                              >
                                <span>{tk}</span>
                                <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                              </Link>
                            ))}
                          </div>

                          {/* Contributing Sources */}
                          {camp.actors.length > 0 && (
                            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs font-mono text-slate-400">
                              <span className="text-slate-400">Sources:</span>
                              {camp.actors.map((actor) => (
                                <span key={actor} className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[11px]">
                                  {actor}
                                </span>
                              ))}
                            </div>
                          )}

                          {/* Relationship Evidence Chips */}
                          <div className="mt-3 flex flex-wrap items-center gap-1.5">
                            {camp.relationship_types.map((rel) => (
                              <span
                                key={rel}
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-800/80 text-slate-300 border border-white/[0.05]"
                                title={camp.relationship_explanations[rel] || rel}
                              >
                                <Sparkles className="h-2.5 w-2.5 text-cyan-400" />
                                {rel.replace("_", " ")}
                              </span>
                            ))}

                            {camp.alert_ids.length > 0 && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-rose-950/40 text-rose-300 border border-rose-500/30">
                                <AlertTriangle className="h-2.5 w-2.5" />
                                {camp.alert_ids.length} Corroborating Alert(s)
                              </span>
                            )}
                          </div>

                          {/* Relationship Explanations */}
                          <div className="mt-3 space-y-1.5">
                            {Object.entries(camp.relationship_explanations).map(([rel, expl]) => (
                              <div key={rel} className="text-xs text-slate-300 bg-black/30 rounded-lg p-2.5 border border-white/[0.04]">
                                <span className="font-mono text-cyan-300 font-semibold uppercase mr-1.5">
                                  [{rel.replace("_", " ")}]:
                                </span>
                                <span>{expl}</span>
                              </div>
                            ))}
                          </div>

                          {/* Context & Potential Contradictions */}
                          {camp.contradictions && camp.contradictions.length > 0 && (
                            <div className="mt-2 space-y-1">
                              {camp.contradictions.map((c, idx) => (
                                <div key={idx} className="text-xs font-mono text-amber-300/80 flex items-center gap-1.5">
                                  <AlertOctagon className="h-3 w-3 text-amber-400 flex-shrink-0" />
                                  <span>{c}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* Top Right: Investigator Actions Toolbar */}
                        <div className="flex flex-row lg:flex-col items-end gap-2 border-t lg:border-t-0 border-white/[0.08] pt-3 lg:pt-0">
                          <button
                            onClick={() => openDetailModal(camp.campaign_id)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-xs font-mono font-semibold text-cyan-300 transition-colors"
                          >
                            <Eye className="h-3.5 w-3.5" />
                            <span>View Full Dossier</span>
                          </button>

                          {camp.status !== "active" && (
                            <button
                              onClick={() => handleCampaignAction(camp.campaign_id, "acknowledge")}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-950/40 hover:bg-emerald-900/50 border border-emerald-500/30 text-[11px] font-mono text-emerald-300"
                            >
                              <CheckCircle2 className="h-3 w-3" />
                              <span>Acknowledge</span>
                            </button>
                          )}

                          {camp.status !== "monitoring" && (
                            <button
                              onClick={() => handleCampaignAction(camp.campaign_id, "monitor")}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 border border-white/[0.08] text-[11px] font-mono text-slate-300"
                            >
                              <Activity className="h-3 w-3" />
                              <span>Monitor</span>
                            </button>
                          )}

                          {camp.status !== "resolved" && (
                            <button
                              onClick={() => handleCampaignAction(camp.campaign_id, "resolve")}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 border border-white/[0.08] text-[11px] font-mono text-slate-300"
                            >
                              <CheckCircle2 className="h-3 w-3" />
                              <span>Resolve</span>
                            </button>
                          )}

                          {camp.status !== "dismissed" && (
                            <button
                              onClick={() => handleCampaignAction(camp.campaign_id, "dismiss")}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 border border-white/[0.08] text-[11px] font-mono text-slate-400"
                            >
                              <XCircle className="h-3 w-3" />
                              <span>Dismiss</span>
                            </button>
                          )}

                          {camp.securities[0] && (
                            <Link
                              href={`/investigate?ticker=${camp.securities[0]}`}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-purple-950/40 hover:bg-purple-900/50 border border-purple-500/30 text-[11px] font-mono text-purple-300"
                            >
                              <TrendingUp className="h-3 w-3" />
                              <span>Forensic Investigation</span>
                            </Link>
                          )}

                          {/* Forensic Exports */}
                          <div className="flex items-center gap-1.5 mt-1">
                            <a
                              href={`${API}/api/campaigns/${camp.campaign_id}/export.pdf`}
                              download={`${camp.campaign_id}_dossier.pdf`}
                              target="_blank"
                              rel="noopener noreferrer"
                              title="Download Forensic PDF Dossier"
                              className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-slate-800 hover:bg-rose-950/50 border border-white/[0.08] hover:border-rose-500/40 text-[10px] font-mono font-semibold text-slate-300 hover:text-rose-300 transition-colors"
                            >
                              <Download className="h-3 w-3 text-rose-400" />
                              <span>PDF</span>
                            </a>
                            <a
                              href={`${API}/api/campaigns/${camp.campaign_id}/export.json`}
                              download={`${camp.campaign_id}_dossier.json`}
                              target="_blank"
                              rel="noopener noreferrer"
                              title="Download Machine-Readable JSON Dossier"
                              className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-slate-800 hover:bg-cyan-950/50 border border-white/[0.08] hover:border-cyan-500/40 text-[10px] font-mono font-semibold text-slate-300 hover:text-cyan-300 transition-colors"
                            >
                              <FileText className="h-3 w-3 text-cyan-400" />
                              <span>JSON</span>
                            </a>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: CHANNEL FINGERPRINT CLUSTERS */}
        {activeTab === "channels" && (
          <div>
            <div className="mb-4">
              <input
                type="text"
                placeholder="Search channel or touched ticker..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full max-w-md pl-4 pr-4 py-2 rounded-lg bg-slate-900 border border-white/[0.08] text-xs font-mono text-slate-200 placeholder:text-slate-500 focus:outline-none"
              />
            </div>

            <div className="space-y-4">
              {channels.map((ch) => {
                const isExpanded = expandedChannels[ch.channel_id];
                return (
                  <div key={ch.channel_id} className="rounded-xl border border-white/[0.08] bg-slate-900/40 p-4">
                    <div
                      className="flex items-center justify-between cursor-pointer"
                      onClick={() => setExpandedChannels((p) => ({ ...p, [ch.channel_id]: !p[ch.channel_id] }))}
                    >
                      <div>
                        <div className="text-sm font-bold text-white flex items-center gap-2">
                          <span>{ch.channel_name}</span>
                          <span className="text-xs font-mono text-slate-400">({ch.total_tips} tips)</span>
                        </div>
                        <div className="text-xs font-mono text-slate-400 mt-1">
                          Entities touched: {ch.entities_touched.join(", ") || "None"} • Ratio: {ch.distinct_ratio_str}
                        </div>
                      </div>
                      <ChevronDown className={`h-4 w-4 text-slate-400 transition-transform ${isExpanded ? "rotate-180" : ""}`} />
                    </div>

                    {isExpanded && (
                      <div className="mt-4 pt-4 border-t border-white/[0.06] space-y-2">
                        {ch.tips.slice(0, 10).map((t, idx) => (
                          <div key={idx} className="text-xs font-mono bg-black/30 p-2 rounded flex justify-between items-center">
                            <span className="text-cyan-300 font-bold">{t.ticker || "UNKNOWN"}</span>
                            <span className="text-slate-400">{t.timestamp || "Recent"}</span>
                            <span className="text-slate-500 font-mono text-[10px]">FP: {t.fingerprint?.slice(0, 8) || "N/A"}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* DETAILED DOSSIER MODAL */}
        {selectedCampaign && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
            <div className="relative w-full max-w-6xl max-h-[90vh] overflow-y-auto rounded-2xl border border-white/[0.15] bg-[#090d14] p-6 shadow-2xl">
              <button
                onClick={() => setSelectedCampaign(null)}
                className="absolute right-4 top-4 p-2 text-slate-400 hover:text-white"
              >
                ✕
              </button>

              <div className="border-b border-white/[0.08] pb-4 mb-4">
                <div className="flex items-center gap-2 text-xs font-mono text-cyan-400 mb-1">
                  <ShieldAlert className="h-4 w-4" />
                  <span>CAMPAIGN DOSSIER • {selectedCampaign.campaign_id}</span>
                </div>
                <h2 className="text-2xl font-bold text-white">{selectedCampaign.name}</h2>
                <div className="flex flex-wrap items-center gap-3 mt-2 text-xs font-mono text-slate-400">
                  <span>Tier: <strong className="text-white">{selectedCampaign.tier}</strong></span>
                  <span>Status: <strong className="text-white">{selectedCampaign.status}</strong></span>
                  <span>Score: <strong className="text-white">{(selectedCampaign.confidence_score * 100).toFixed(0)}%</strong></span>
                  <span>Time Span: {formatTimeWindow(selectedCampaign.first_seen, selectedCampaign.last_seen)}</span>
                </div>

                {/* Forensic Dossier Export Actions */}
                <div className="flex flex-wrap items-center gap-2 mt-4 pt-3 border-t border-white/[0.06]">
                  <a
                    href={`${API}/api/campaigns/${selectedCampaign.campaign_id}/export.pdf`}
                    download={`${selectedCampaign.campaign_id}_dossier.pdf`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/30 text-xs font-mono font-bold text-rose-300 transition-colors shadow-sm"
                  >
                    <Download className="h-3.5 w-3.5 text-rose-400" />
                    <span>Export Forensic PDF Dossier</span>
                  </a>

                  <a
                    href={`${API}/api/campaigns/${selectedCampaign.campaign_id}/export.json`}
                    download={`${selectedCampaign.campaign_id}_dossier.json`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-xs font-mono font-bold text-cyan-300 transition-colors shadow-sm"
                  >
                    <FileText className="h-3.5 w-3.5 text-cyan-400" />
                    <span>Export Structured JSON Dossier</span>
                  </a>

                  {selectedCampaign.securities[0] && (
                    <Link
                      href={`/investigate?ticker=${selectedCampaign.securities[0]}`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500/15 hover:bg-purple-500/25 border border-purple-500/30 text-xs font-mono font-bold text-purple-300 transition-colors shadow-sm"
                    >
                      <TrendingUp className="h-3.5 w-3.5 text-purple-400" />
                      <span>Forensic Investigation View</span>
                    </Link>
                  )}
                </div>
              </div>

              {/* Connected Securities */}
              <div className="mb-6">
                <h4 className="text-xs font-mono uppercase text-slate-400 mb-2">Connected Securities</h4>
                <div className="flex flex-wrap gap-2">
                  {selectedCampaign.securities.map((tk) => (
                    <Link
                      key={tk}
                      href={`/stocks/${tk}`}
                      target="_blank"
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-cyan-950 border border-white/[0.08] text-xs font-mono font-bold text-cyan-300 flex items-center gap-1.5"
                    >
                      <span>{tk}</span>
                      <ExternalLink className="h-3 w-3" />
                    </Link>
                  ))}
                </div>
              </div>

              {/* Interactive Evidence-Backed Syndicate Graph */}
              <div className="mb-6">
                <CampaignGraph campaignId={selectedCampaign.campaign_id} />
              </div>

              {/* Chronological Event Timeline */}
              <div className="mb-6">
                <h4 className="text-xs font-mono uppercase text-slate-400 mb-2 flex items-center justify-between">
                  <span>Chronological Forensic Timeline ({selectedCampaign.events?.length || 0} events)</span>
                  <span className="text-[10px] text-slate-500 font-mono">Original publication vs ingestion</span>
                </h4>

                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                  {selectedCampaign.events && selectedCampaign.events.length > 0 ? (
                    selectedCampaign.events.map((ev) => (
                      <div key={ev.event_id} className="rounded-lg border border-white/[0.05] bg-black/40 p-3 text-xs">
                        <div className="flex items-center justify-between font-mono text-[11px] text-slate-400 mb-1">
                          <span className="font-bold text-cyan-300 uppercase">
                            [{ev.event_type}] {ev.ticker}
                          </span>
                          <span>Pub: {ev.event_timestamp}</span>
                        </div>
                        <div className="text-slate-200">{ev.summary}</div>
                        <div className="mt-1 text-[10px] font-mono text-slate-500 flex items-center justify-between">
                          <span>Source: {ev.source_label}</span>
                          <span>Freshness: {ev.data_freshness} • Ingested: {ev.retrieved_at}</span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-xs font-mono text-slate-500 py-4 text-center">
                      No chronological events logged.
                    </div>
                  )}
                </div>
              </div>

              {/* Investigator Notes */}
              <div className="mb-6">
                <h4 className="text-xs font-mono uppercase text-slate-400 mb-2">Investigator Notes &amp; Audit Trail</h4>
                {selectedCampaign.notes ? (
                  <pre className="text-xs font-mono bg-black/50 p-3 rounded-lg text-slate-300 whitespace-pre-wrap max-h-32 overflow-y-auto mb-3">
                    {selectedCampaign.notes}
                  </pre>
                ) : (
                  <div className="text-xs font-mono text-slate-500 mb-2">No notes recorded yet.</div>
                )}

                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder="Add an investigative note..."
                    value={newNote}
                    onChange={(e) => setNewNote(e.target.value)}
                    className="flex-1 rounded-lg bg-slate-900 border border-white/[0.08] px-3 py-1.5 text-xs font-mono text-slate-200 focus:outline-none"
                  />
                  <button
                    onClick={handleAddNote}
                    disabled={savingNote || !newNote.trim()}
                    className="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-xs font-mono font-bold text-white disabled:opacity-50"
                  >
                    {savingNote ? "Saving..." : "Add Note"}
                  </button>
                </div>
              </div>

              {/* Actions Footer */}
              <div className="flex items-center justify-between pt-4 border-t border-white/[0.08]">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleCampaignAction(selectedCampaign.campaign_id, "acknowledge")}
                    className="px-3 py-1.5 rounded-md bg-emerald-950/60 hover:bg-emerald-900 border border-emerald-500/30 text-xs font-mono text-emerald-300"
                  >
                    Acknowledge
                  </button>
                  <button
                    onClick={() => handleCampaignAction(selectedCampaign.campaign_id, "monitor")}
                    className="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 border border-white/[0.08] text-xs font-mono text-slate-300"
                  >
                    Monitor
                  </button>
                  <button
                    onClick={() => handleCampaignAction(selectedCampaign.campaign_id, "resolve")}
                    className="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 border border-white/[0.08] text-xs font-mono text-slate-300"
                  >
                    Resolve
                  </button>
                  <button
                    onClick={() => handleCampaignAction(selectedCampaign.campaign_id, "dismiss")}
                    className="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 border border-white/[0.08] text-xs font-mono text-slate-400"
                  >
                    Dismiss
                  </button>
                </div>

                <button
                  onClick={() => setSelectedCampaign(null)}
                  className="px-4 py-1.5 rounded-md bg-slate-800 text-xs font-mono text-slate-300"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}