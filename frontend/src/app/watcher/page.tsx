"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import {
  Eye,
  ShieldAlert,
  AlertTriangle,
  Activity,
  Radar,
  Zap,
  Clock,
  ArrowUpRight,
  ShieldCheck,
  Layers,
  Radio,
  RefreshCw,
  Bell,
  CheckCircle2,
  XCircle,
  Sliders,
  Send,
  AlertCircle,
  ExternalLink,
  Search,
  Filter,
} from "lucide-react";

type AlertRecord = {
  alert_id: string;
  rule_id: string;
  rule_name: string;
  rule_type: string;
  ticker: string;
  severity: "info" | "warning" | "critical";
  status: "active" | "acknowledged" | "dismissed" | "resolved";
  title: string;
  message: string;
  trigger_value?: number | null;
  trigger_value_str?: string | null;
  threshold_value?: number | null;
  threshold_value_str?: string | null;
  observation_timestamp?: string | null;
  retrieved_at?: string | null;
  data_freshness: string;
  feed_type: string;
  dedup_key: string;
  evidence_context?: Record<string, any>;
  jev_assessment?: Record<string, any> | null;
  created_at: string;
  acknowledged_at?: string | null;
  dismissed_at?: string | null;
  telegram_delivery_status?: string;
  telegram_message_id?: string | null;
  telegram_error?: string | null;
};

type AlertRule = {
  rule_id: string;
  name: string;
  ticker: string;
  scope: string;
  rule_type: string;
  condition: string;
  threshold?: number | null;
  threshold_str?: string | null;
  severity: "info" | "warning" | "critical";
  enabled: boolean;
  cooldown_seconds: number;
  notify_terminal: boolean;
  notify_telegram: boolean;
  auto_investigate: boolean;
  last_triggered_at?: string | null;
  trigger_count: number;
};

type AlertSummary = {
  total_alerts: number;
  active_alerts: number;
  unread_alerts: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
  active_rules: number;
  last_evaluation_time?: string | null;
  engine_status: string;
};

type Holding = {
  ticker: string;
  name: string;
  exchange: string;
  quantity: number;
  average_buy_price: number | null;
  risk?: {
    score?: number;
    band?: string;
    reasons?: string[];
  } | null;
};

type Portfolio = {
  name: string;
  holdings: Holding[];
};

export default function WatcherPage() {
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [engineStatus, setEngineStatus] = useState<Record<string, any> | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);

  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState("");
  const [lastRefreshed, setLastRefreshed] = useState("");

  const [activeTab, setActiveTab] = useState<"alerts" | "rules" | "radar">("alerts");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [alertsRes, summaryRes, rulesRes, statusRes, portfolioRes] = await Promise.all([
        fetch(`${API}/api/alerts?status=${statusFilter}&severity=${severityFilter}&limit=100`, { cache: "no-store" }),
        fetch(`${API}/api/alerts/summary`, { cache: "no-store" }),
        fetch(`${API}/api/alerts/rules`, { cache: "no-store" }),
        fetch(`${API}/api/alerts/status`, { cache: "no-store" }),
        fetch(`${API}/api/portfolio`, { cache: "no-store" }).catch(() => null),
      ]);

      if (alertsRes.ok) {
        const d = await alertsRes.json();
        setAlerts(d.alerts || []);
      }
      if (summaryRes.ok) {
        const d = await summaryRes.json();
        setSummary(d.summary || null);
      }
      if (rulesRes.ok) {
        const d = await rulesRes.json();
        setRules(d.rules || []);
      }
      if (statusRes.ok) {
        const d = await statusRes.json();
        setEngineStatus(d || null);
      }
      if (portfolioRes && portfolioRes.ok) {
        const d = await portfolioRes.json();
        setPortfolio(d || null);
      }

      setLastRefreshed(
        new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) + " IST"
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed loading monitoring and alert data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 20000);
    return () => clearInterval(interval);
  }, [severityFilter, statusFilter]);

  async function handleAcknowledge(alertId: string) {
    try {
      const res = await fetch(`${API}/api/alerts/${alertId}/acknowledge`, { method: "POST" });
      if (res.ok) {
        setAlerts((prev) =>
          prev.map((a) => (a.alert_id === alertId ? { ...a, status: "acknowledged" } : a))
        );
        if (summary) {
          setSummary({ ...summary, active_alerts: Math.max(0, summary.active_alerts - 1) });
        }
      }
    } catch (err) {
      console.error("Error acknowledging alert:", err);
    }
  }

  async function handleDismiss(alertId: string) {
    try {
      const res = await fetch(`${API}/api/alerts/${alertId}/dismiss`, { method: "POST" });
      if (res.ok) {
        setAlerts((prev) =>
          prev.map((a) => (a.alert_id === alertId ? { ...a, status: "dismissed" } : a))
        );
        if (summary) {
          setSummary({ ...summary, active_alerts: Math.max(0, summary.active_alerts - 1) });
        }
      }
    } catch (err) {
      console.error("Error dismissing alert:", err);
    }
  }

  async function handleToggleRule(ruleId: string) {
    try {
      const res = await fetch(`${API}/api/alerts/rules/${ruleId}/toggle`, { method: "POST" });
      if (res.ok) {
        const d = await res.json();
        setRules((prev) =>
          prev.map((r) => (r.rule_id === ruleId ? { ...r, enabled: d.enabled } : r))
        );
      }
    } catch (err) {
      console.error("Error toggling rule:", err);
    }
  }

  async function handleEvaluateNow() {
    try {
      setEvaluating(true);
      await fetch(`${API}/api/alerts/evaluate`, { method: "POST" });
      await loadData();
    } catch (err) {
      console.error("Evaluation error:", err);
    } finally {
      setEvaluating(false);
    }
  }

  const filteredAlerts = useMemo(() => {
    let result = alerts;
    if (searchQuery.trim()) {
      const q = searchQuery.toUpperCase().trim();
      result = result.filter(
        (a) => a.ticker.includes(q) || a.rule_name.toUpperCase().includes(q) || a.title.toUpperCase().includes(q)
      );
    }
    return result;
  }, [alerts, searchQuery]);

  function severityBadge(sev: string) {
    if (sev === "critical") {
      return (
        <span className="inline-flex items-center gap-1 rounded-md border border-rose-500/40 bg-rose-950/60 px-2 py-0.5 text-[11px] font-mono font-bold text-rose-300">
          <AlertCircle className="h-3 w-3 text-rose-400" />
          CRITICAL
        </span>
      );
    }
    if (sev === "warning") {
      return (
        <span className="inline-flex items-center gap-1 rounded-md border border-amber-500/40 bg-amber-950/60 px-2 py-0.5 text-[11px] font-mono font-bold text-amber-300">
          <AlertTriangle className="h-3 w-3 text-amber-400" />
          WARNING
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-sky-500/40 bg-sky-950/60 px-2 py-0.5 text-[11px] font-mono font-bold text-sky-300">
        <Activity className="h-3 w-3 text-sky-400" />
        INFO
      </span>
    );
  }

  function freshnessBadge(status: string) {
    const s = status.toLowerCase();
    if (s === "live") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-mono font-semibold text-emerald-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          LIVE
        </span>
      );
    }
    if (s === "delayed") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-mono font-semibold text-cyan-400">
          <Clock className="h-2.5 w-2.5 text-cyan-400" />
          DELAYED
        </span>
      );
    }
    if (s === "stale") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-mono font-semibold text-amber-400">
          <AlertTriangle className="h-2.5 w-2.5 text-amber-400" />
          STALE
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-800/60 px-2 py-0.5 text-[10px] font-mono font-semibold text-slate-300">
        CACHED
      </span>
    );
  }

  return (
    <main className="min-h-screen bg-[#05070a] text-zinc-100 bg-terminal-grid">
      <Navbar />

      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Header Ribbon */}
        <div className="mb-6 flex flex-col justify-between gap-4 border-b border-zinc-800 pb-5 md:flex-row md:items-end">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono tracking-wider text-rose-400 uppercase">
              <Radar className="h-4 w-4 animate-spin text-rose-500" style={{ animationDuration: "6s" }} />
              DAKOTA INTELLIGENT SURVEILLANCE & ALERTING TERMINAL
            </div>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-white sm:text-3xl font-mono">
              Surveillance Watcher & Alert Center
            </h1>
            <p className="mt-1 text-xs text-zinc-400 font-mono">
              Deterministic threshold crossing monitoring, market anomaly detection, and JEV forensic integration.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleEvaluateNow}
              disabled={evaluating}
              className="flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-950/40 px-3.5 py-1.5 text-xs font-mono font-semibold text-rose-300 hover:bg-rose-900/60 disabled:opacity-50 transition"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${evaluating ? "animate-spin" : ""}`} />
              {evaluating ? "Evaluating..." : "Evaluate Rules Now"}
            </button>

            <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-1.5 text-xs font-mono text-zinc-400">
              <Clock className="h-3.5 w-3.5 text-zinc-500" />
              <span>{lastRefreshed || "Syncing..."}</span>
            </div>
          </div>
        </div>

        {/* Operational Telemetry Metrics */}
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="text-[11px] font-mono text-zinc-400 uppercase">Active Alerts</div>
            <div className="mt-1 text-2xl font-bold font-mono text-white">
              {summary?.active_alerts ?? 0}
            </div>
            <div className="mt-1 text-[10px] font-mono text-zinc-500">Unresolved events</div>
          </div>

          <div className="rounded-xl border border-rose-500/20 bg-rose-950/20 p-4">
            <div className="text-[11px] font-mono text-rose-400 uppercase">Critical Severity</div>
            <div className="mt-1 text-2xl font-bold font-mono text-rose-300">
              {summary?.critical_count ?? 0}
            </div>
            <div className="mt-1 text-[10px] font-mono text-rose-400/70">Urgent forensic breaches</div>
          </div>

          <div className="rounded-xl border border-amber-500/20 bg-amber-950/20 p-4">
            <div className="text-[11px] font-mono text-amber-400 uppercase">Warnings</div>
            <div className="mt-1 text-2xl font-bold font-mono text-amber-300">
              {summary?.warning_count ?? 0}
            </div>
            <div className="mt-1 text-[10px] font-mono text-amber-400/70">Threshold crossings</div>
          </div>

          <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="text-[11px] font-mono text-zinc-400 uppercase">Active Rules</div>
            <div className="mt-1 text-2xl font-bold font-mono text-white">
              {summary?.active_rules ?? rules.filter((r) => r.enabled).length}
            </div>
            <div className="mt-1 text-[10px] font-mono text-zinc-500">Monitored triggers</div>
          </div>

          <div className="col-span-2 sm:col-span-1 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="text-[11px] font-mono text-zinc-400 uppercase">Telegram Delivery</div>
            <div className="mt-1 flex items-center gap-1.5 text-xs font-mono font-bold">
              {engineStatus?.telegram?.configured ? (
                <span className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  ONLINE
                </span>
              ) : (
                <span className="flex items-center gap-1 text-zinc-400" title="Configure TELEGRAM_ALERT_CHAT_ID in .env">
                  <XCircle className="h-3.5 w-3.5 text-zinc-500" />
                  OPTIONAL
                </span>
              )}
            </div>
            <div className="mt-1 text-[10px] font-mono text-zinc-500">
              {engineStatus?.telegram?.configured ? "Bot connected" : "In-terminal active"}
            </div>
          </div>
        </div>

        {/* Tabs & Filters */}
        <div className="mb-6 flex flex-col gap-4 border-b border-zinc-800 pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab("alerts")}
              className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-mono font-semibold transition ${
                activeTab === "alerts"
                  ? "border border-rose-500/30 bg-rose-950/60 text-rose-300"
                  : "border border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:text-white"
              }`}
            >
              <Bell className="h-3.5 w-3.5" />
              Alert Stream ({alerts.length})
            </button>

            <button
              onClick={() => setActiveTab("rules")}
              className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-mono font-semibold transition ${
                activeTab === "rules"
                  ? "border border-rose-500/30 bg-rose-950/60 text-rose-300"
                  : "border border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:text-white"
              }`}
            >
              <Sliders className="h-3.5 w-3.5" />
              Monitoring Rules ({rules.length})
            </button>

            <button
              onClick={() => setActiveTab("radar")}
              className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-mono font-semibold transition ${
                activeTab === "radar"
                  ? "border border-rose-500/30 bg-rose-950/60 text-rose-300"
                  : "border border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:text-white"
              }`}
            >
              <Eye className="h-3.5 w-3.5" />
              Security Radar
            </button>
          </div>

          {activeTab === "alerts" && (
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500" />
                <input
                  type="text"
                  placeholder="Filter ticker or rule..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="rounded-lg border border-zinc-800 bg-zinc-900/80 pl-8 pr-3 py-1.5 text-xs font-mono text-zinc-200 placeholder-zinc-500 focus:border-rose-500/50 focus:outline-none"
                />
              </div>

              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                className="rounded-lg border border-zinc-800 bg-zinc-900/80 px-2.5 py-1.5 text-xs font-mono text-zinc-300 focus:border-rose-500/50 focus:outline-none"
              >
                <option value="all">All Severities</option>
                <option value="critical">Critical</option>
                <option value="warning">Warning</option>
                <option value="info">Info</option>
              </select>

              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="rounded-lg border border-zinc-800 bg-zinc-900/80 px-2.5 py-1.5 text-xs font-mono text-zinc-300 focus:border-rose-500/50 focus:outline-none"
              >
                <option value="all">All Statuses</option>
                <option value="active">Active Only</option>
                <option value="acknowledged">Acknowledged</option>
                <option value="dismissed">Dismissed</option>
              </select>
            </div>
          )}
        </div>

        {/* Tab 1: Alert Stream */}
        {activeTab === "alerts" && (
          <div className="space-y-3">
            {filteredAlerts.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-zinc-800 py-16 text-center">
                <ShieldCheck className="h-10 w-10 text-emerald-400/80" />
                <h3 className="mt-3 text-sm font-mono font-bold text-white">No Matching Alerts</h3>
                <p className="mt-1 max-w-sm text-xs font-mono text-zinc-400">
                  All monitored securities are within configured thresholds. No active breaches or anomalies recorded.
                </p>
                <button
                  onClick={handleEvaluateNow}
                  className="mt-4 rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-1.5 text-xs font-mono text-zinc-200 hover:bg-zinc-700"
                >
                  Run Instant Evaluation
                </button>
              </div>
            ) : (
              filteredAlerts.map((alt) => (
                <div
                  key={alt.alert_id}
                  className={`rounded-xl border p-4 transition ${
                    alt.status === "dismissed"
                      ? "border-zinc-800/40 bg-zinc-950/40 opacity-60"
                      : alt.severity === "critical"
                      ? "border-rose-500/30 bg-rose-950/15"
                      : alt.severity === "warning"
                      ? "border-amber-500/30 bg-amber-950/15"
                      : "border-zinc-800 bg-zinc-900/40"
                  }`}
                >
                  <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start">
                    <div className="flex flex-wrap items-center gap-2">
                      {severityBadge(alt.severity)}
                      <Link
                        href={`/stocks/${alt.ticker}`}
                        className="font-mono text-base font-bold text-white hover:text-rose-400 transition flex items-center gap-1"
                      >
                        {alt.ticker}
                        <ArrowUpRight className="h-3.5 w-3.5 text-zinc-500" />
                      </Link>
                      <span className="text-zinc-500 font-mono text-xs">•</span>
                      <span className="text-xs font-mono font-medium text-zinc-300">{alt.rule_name}</span>
                      <span className="text-zinc-500 font-mono text-xs">•</span>
                      {freshnessBadge(alt.data_freshness)}
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-mono text-zinc-400">
                        {new Date(alt.created_at).toLocaleTimeString("en-IN", {
                          timeZone: "Asia/Kolkata",
                          hour12: false,
                        })}{" "}
                        IST
                      </span>
                      {alt.status === "active" && (
                        <div className="flex items-center gap-1.5 ml-2">
                          <button
                            onClick={() => handleAcknowledge(alt.alert_id)}
                            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-[10px] font-mono text-zinc-300 hover:bg-zinc-700 transition"
                          >
                            Acknowledge
                          </button>
                          <button
                            onClick={() => handleDismiss(alt.alert_id)}
                            className="rounded border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] font-mono text-zinc-400 hover:text-zinc-200 transition"
                          >
                            Dismiss
                          </button>
                        </div>
                      )}
                      {alt.status === "acknowledged" && (
                        <span className="rounded bg-sky-950/60 border border-sky-800/40 px-2 py-0.5 text-[10px] font-mono text-sky-400">
                          ACKNOWLEDGED
                        </span>
                      )}
                      {alt.status === "dismissed" && (
                        <span className="rounded bg-zinc-800/60 border border-zinc-700/40 px-2 py-0.5 text-[10px] font-mono text-zinc-400">
                          DISMISSED
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="mt-2 text-sm font-semibold text-zinc-100 font-mono">{alt.title}</div>
                  <p className="mt-1 text-xs text-zinc-400 font-mono leading-relaxed">{alt.message}</p>

                  {/* Context & Metadata Row */}
                  <div className="mt-3 flex flex-wrap items-center gap-4 text-[10px] font-mono text-zinc-500 border-t border-zinc-800/60 pt-2">
                    <div>
                      Observed: <span className="text-zinc-300">{alt.observation_timestamp || "Session"}</span>
                    </div>
                    <div>
                      Retrieved: <span className="text-zinc-300">{alt.retrieved_at ? alt.retrieved_at.slice(11, 19) + " UTC" : "N/A"}</span>
                    </div>
                    <div>
                      Feed: <span className="text-zinc-300">{alt.feed_type}</span>
                    </div>
                    {alt.telegram_delivery_status === "sent" && (
                      <div className="text-emerald-400 flex items-center gap-1">
                        <Send className="h-2.5 w-2.5" /> Dispatched to Telegram
                      </div>
                    )}
                    <div className="ml-auto flex items-center gap-2">
                      <Link
                        href={`/investigate?ticker=${alt.ticker}`}
                        className="text-rose-400 hover:underline flex items-center gap-1"
                      >
                        Investigate Scrip <ExternalLink className="h-2.5 w-2.5" />
                      </Link>
                    </div>
                  </div>

                  {/* JEV Grounded Intelligence Banner if Present */}
                  {alt.jev_assessment && (
                    <div className="mt-2.5 rounded-lg border border-purple-500/20 bg-purple-950/20 p-2.5 text-xs font-mono text-purple-300">
                      <div className="flex items-center gap-1.5 font-bold text-purple-400">
                        <Zap className="h-3 w-3" />
                        JEV Evidence Assessment:
                      </div>
                      <p className="mt-1 text-[11px] text-purple-200/90">
                        {alt.jev_assessment?.analysis?.executive_summary || "Contextual evidence analysis generated."}
                      </p>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {/* Tab 2: Monitoring Rules */}
        {activeTab === "rules" && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-mono font-bold text-white">Configured Alert Rules</h3>
                <p className="text-xs font-mono text-zinc-400">
                  Rules evaluate automatically on incoming market sync cycles and risk assessments.
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-500 uppercase text-[10px]">
                    <th className="pb-2">Rule Name</th>
                    <th className="pb-2">Scope / Target</th>
                    <th className="pb-2">Condition</th>
                    <th className="pb-2">Severity</th>
                    <th className="pb-2">Cooldown</th>
                    <th className="pb-2">Telegram</th>
                    <th className="pb-2">Triggered</th>
                    <th className="pb-2 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {rules.map((rule) => (
                    <tr key={rule.rule_id} className="hover:bg-zinc-800/20">
                      <td className="py-2.5 font-medium text-white">{rule.name}</td>
                      <td className="py-2.5 text-zinc-400">
                        <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-300">
                          {rule.scope.toUpperCase()}: {rule.ticker}
                        </span>
                      </td>
                      <td className="py-2.5 text-zinc-300">
                        {rule.rule_type} {rule.condition} {rule.threshold ?? rule.threshold_str}
                      </td>
                      <td className="py-2.5">{severityBadge(rule.severity)}</td>
                      <td className="py-2.5 text-zinc-400">{rule.cooldown_seconds}s</td>
                      <td className="py-2.5 text-zinc-400">
                        {rule.notify_telegram ? (
                          <span className="text-emerald-400">Enabled</span>
                        ) : (
                          <span className="text-zinc-600">Terminal Only</span>
                        )}
                      </td>
                      <td className="py-2.5 text-zinc-400">{rule.trigger_count} times</td>
                      <td className="py-2.5 text-right">
                        <button
                          onClick={() => handleToggleRule(rule.rule_id)}
                          className={`rounded px-2.5 py-1 text-[10px] font-mono font-bold transition ${
                            rule.enabled
                              ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25"
                              : "bg-zinc-800 text-zinc-500 border border-zinc-700 hover:text-zinc-300"
                          }`}
                        >
                          {rule.enabled ? "ACTIVE" : "DISABLED"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 3: Security Radar */}
        {activeTab === "radar" && (
          <div className="space-y-4">
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
              <h3 className="text-sm font-mono font-bold text-white">Portfolio Security Radar</h3>
              <p className="text-xs font-mono text-zinc-400">
                Holdings monitored for active manipulation patterns, promoter pledging, and forensic risk signals.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {(portfolio?.holdings || []).map((h) => (
                <div key={h.ticker} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <Link
                        href={`/stocks/${h.ticker}`}
                        className="font-mono text-base font-bold text-white hover:text-rose-400 transition"
                      >
                        {h.ticker}
                      </Link>
                      <div className="text-[11px] text-zinc-400 font-mono">{h.name}</div>
                    </div>
                    <span
                      className={`rounded-full border px-2.5 py-0.5 text-xs font-mono font-bold ${
                        h.risk?.band === "High"
                          ? "border-rose-500/40 bg-rose-950/40 text-rose-300"
                          : h.risk?.band === "Elevated"
                          ? "border-amber-500/40 bg-amber-950/40 text-amber-300"
                          : "border-emerald-500/40 bg-emerald-950/40 text-emerald-300"
                      }`}
                    >
                      {h.risk?.score ? `${h.risk.score.toFixed(1)} (${h.risk.band})` : "Assessed"}
                    </span>
                  </div>

                  <div className="mt-3 space-y-1">
                    {(h.risk?.reasons || []).slice(0, 3).map((r, i) => (
                      <div key={i} className="text-[11px] font-mono text-zinc-400 flex items-start gap-1.5">
                        <span className="text-rose-500 mt-0.5">•</span>
                        <span>{r}</span>
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 border-t border-zinc-800/60 pt-2 flex items-center justify-between">
                    <Link
                      href={`/stocks/${h.ticker}`}
                      className="text-xs font-mono text-zinc-400 hover:text-white flex items-center gap-1"
                    >
                      Security Page <ArrowUpRight className="h-3 w-3" />
                    </Link>
                    <Link
                      href={`/investigate?ticker=${h.ticker}`}
                      className="text-xs font-mono text-rose-400 hover:underline flex items-center gap-1"
                    >
                      Investigate <ExternalLink className="h-3 w-3" />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}