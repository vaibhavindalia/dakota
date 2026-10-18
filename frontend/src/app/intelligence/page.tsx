"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import {
  Sparkles,
  Bot,
  Send,
  RefreshCw,
  FileText,
  Search,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Copy,
  Check,
  Trash2,
  Plus,
  ChevronRight,
  Info,
  X,
  Flag,
  Clock,
  ArrowUpRight,
  Download,
  Printer,
  TrendingUp,
  Layers,
  Radio,
  Cpu,
  ArrowLeft,
  Activity,
  Zap,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type EvidenceItem = {
  id: string;
  type: string;
  title: string;
  snippet: string;
  source_name: string;
  source_url: string | null;
  entity_id: string | null;
  published_at: string | null;
  confidence: number;
  verified: boolean;
  observation_type: string;
  metadata?: Record<string, any>;
};

type Citation = {
  index: number;
  evidence_id: string;
  label: string;
  source_name: string;
  source_url: string | null;
  snippet: string;
  observation_type: string;
};

type ClaimFinding = {
  id: string;
  claim: string;
  status: string;
  supporting_evidence_ids: string[];
  severity: string;
  confidence: number;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  evidence?: EvidenceItem[];
  findings?: ClaimFinding[];
  contradictions?: string[];
  followups?: string[];
  confidence_score?: number;
  created_at?: string;
  isStreaming?: boolean;
};

type Conversation = {
  id: string;
  title: string;
  updated_at: string;
};

type SearchResult = {
  id: string;
  type: string;
  title: string;
  subtitle: string;
  snippet: string;
  score: number | null;
  band: string | null;
  url: string | null;
};

const SAMPLE_PROMPTS = [
  "Summarize the key news and forensic risks affecting VARANIUM.",
  "Why did this stock's risk score change?",
  "Find connections between promotional tips and recent market moves.",
  "Investigate CLOUD using all available news and intake evidence.",
  "Compare latest information with previous findings.",
  "Generate a comprehensive intelligence brief for RELIANCE.",
];

export default function IntelligencePage() {
  const [activeTab, setActiveTab] = useState<"copilot" | "search" | "report">("copilot");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputQuery, setInputQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeTickerContext, setActiveTickerContext] = useState("");
  const [systemStatus, setSystemStatus] = useState<any>(null);

  // Evidence Inspector drawer state
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [activeEvidenceList, setActiveEvidenceList] = useState<EvidenceItem[]>([]);
  const [selectedEvidenceItem, setSelectedEvidenceItem] = useState<EvidenceItem | null>(null);

  // Feedback modal
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackItemTarget, setFeedbackItemTarget] = useState<EvidenceItem | null>(null);
  const [feedbackNotes, setFeedbackNotes] = useState("");
  const [feedbackSent, setFeedbackSent] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFilterType, setSearchFilterType] = useState("");
  const [searchBand, setSearchBand] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // Report Generator state
  const [reportTicker, setReportTicker] = useState("VARANIUM");
  const [reportType, setReportType] = useState("company_brief");
  const [generatedReport, setGeneratedReport] = useState<any>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [copiedReport, setCopiedReport] = useState(false);

  // Copy message state
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Diagnostics modal state
  const [diagOpen, setDiagOpen] = useState(false);
  const [diagLoading, setDiagLoading] = useState(false);
  const [diagData, setDiagData] = useState<any>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load system status & conversations on mount
  useEffect(() => {
    fetchSystemStatus();
    loadConversations();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function fetchSystemStatus() {
    try {
      const res = await fetch(`${API}/api/intelligence/status`);
      if (res.ok) {
        const data = await res.json();
        setSystemStatus(data);
      }
    } catch {
      // ignore
    }
  }

  async function openDiagnostics() {
    setDiagOpen(true);
    setDiagLoading(true);
    try {
      const res = await fetch(`${API}/api/intelligence/test-provider`);
      if (res.ok) {
        const data = await res.json();
        setDiagData(data);
      }
    } catch {
      // ignore
    } finally {
      setDiagLoading(false);
    }
  }

  async function loadConversations() {
    try {
      const res = await fetch(`${API}/api/intelligence/conversations`);
      if (res.ok) {
        const data = await res.json();
        const items = data.conversations || [];
        setConversations(items);
        if (items.length > 0 && !currentConversationId) {
          selectConversation(items[0].id);
        }
      }
    } catch {
      // ignore
    }
  }

  async function selectConversation(cid: string) {
    setCurrentConversationId(cid);
    try {
      const res = await fetch(`${API}/api/intelligence/conversations/${cid}`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch {
      // ignore
    }
  }

  async function startNewSession() {
    try {
      const res = await fetch(`${API}/api/intelligence/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "New Intelligence Session" }),
      });
      if (res.ok) {
        const data = await res.json();
        setConversations((prev) => [data, ...prev]);
        setCurrentConversationId(data.id);
        setMessages([]);
      }
    } catch {
      const tempId = "session_" + Date.now();
      setCurrentConversationId(tempId);
      setMessages([]);
    }
  }

  async function deleteSession(cid: string, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await fetch(`${API}/api/intelligence/conversations/${cid}`, { method: "DELETE" });
      setConversations((prev) => prev.filter((c) => c.id !== cid));
      if (currentConversationId === cid) {
        setMessages([]);
        setCurrentConversationId("");
      }
    } catch {
      // ignore
    }
  }

  async function handleSendMessage(overrideQuery?: string) {
    const q = (overrideQuery || inputQuery).trim();
    if (!q || loading) return;

    setInputQuery("");
    const userMsg: Message = {
      id: "u_" + Date.now(),
      role: "user",
      content: q,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    const assistantMsgId = "a_" + Date.now();
    const assistantMsgPlaceholder: Message = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      isStreaming: true,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, assistantMsgPlaceholder]);

    try {
      // Try SSE stream
      const streamUrl = `${API}/api/intelligence/query/stream?query=${encodeURIComponent(q)}${
        currentConversationId ? `&conversation_id=${currentConversationId}` : ""
      }${activeTickerContext ? `&ticker=${encodeURIComponent(activeTickerContext)}` : ""}`;

      const response = await fetch(streamUrl);

      if (!response.ok || !response.body) {
        // Fallback to synchronous endpoint
        const fallbackRes = await fetch(`${API}/api/intelligence/query`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: q,
            conversation_id: currentConversationId || undefined,
            active_context: activeTickerContext ? { ticker: activeTickerContext } : {},
          }),
        });
        if (fallbackRes.ok) {
          const fbData = await fallbackRes.json();
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: fbData.detailed_text,
                    citations: fbData.citations,
                    evidence: fbData.evidence_items,
                    findings: fbData.findings,
                    contradictions: fbData.contradictions,
                    followups: fbData.suggested_followups,
                    confidence_score: fbData.confidence_score,
                    isStreaming: false,
                  }
                : m
            )
          );
          if (fbData.evidence_items?.length) {
            setActiveEvidenceList(fbData.evidence_items);
          }
        }
        setLoading(false);
        loadConversations();
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let accumulated = "";
      let retrievedEvidence: EvidenceItem[] = [];

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === "retrieval_complete") {
                retrievedEvidence = data.evidence_items || [];
                setActiveEvidenceList(retrievedEvidence);
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId ? { ...m, evidence: retrievedEvidence } : m
                  )
                );
              } else if (data.type === "content_chunk") {
                accumulated += data.chunk;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId ? { ...m, content: accumulated } : m
                  )
                );
              } else if (data.type === "done") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? {
                          ...m,
                          content: accumulated,
                          citations: data.citations,
                          findings: data.findings,
                          contradictions: data.contradictions,
                          followups: data.followups,
                          isStreaming: false,
                        }
                      : m
                  )
                );
              }
            } catch {
              // ignore parse errors on partial chunks
            }
          }
        }
      }

      loadConversations();
    } catch (err: any) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? {
                ...m,
                content: `⚠️ Connection notice: ${err?.message || "Could not complete request."}`,
                isStreaming: false,
              }
            : m
        )
      );
    } finally {
      setLoading(false);
    }
  }

  function openInspectorWithEvidence(evidenceList: EvidenceItem[], specificItem?: EvidenceItem) {
    setActiveEvidenceList(evidenceList);
    setSelectedEvidenceItem(specificItem || evidenceList[0] || null);
    setInspectorOpen(true);
  }

  function handleCitationClick(label: string, evidenceList?: EvidenceItem[]) {
    const tag = label.replace(/[\[\]]/g, "");
    const list = evidenceList || activeEvidenceList;
    const target = list.find((e) => e.id === tag);
    if (target) {
      openInspectorWithEvidence(list, target);
    } else if (list.length > 0) {
      openInspectorWithEvidence(list, list[0]);
    }
  }

  function copyToClipboard(text: string, id: string) {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }

  // Cross-module search execution
  async function handleSearch(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!searchQuery.trim()) return;

    setSearchLoading(true);
    try {
      const params = new URLSearchParams({
        search: searchQuery.trim(),
        types: searchFilterType,
        band: searchBand,
        limit: "15",
      });
      const res = await fetch(`${API}/api/intelligence/search?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data.results || []);
      }
    } catch {
      // ignore
    } finally {
      setSearchLoading(false);
    }
  }

  // Report Generator execution
  async function handleGenerateReport() {
    setReportLoading(true);
    try {
      const res = await fetch(`${API}/api/intelligence/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: reportTicker.trim().toUpperCase(),
          report_type: reportType,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setGeneratedReport(data);
      }
    } catch {
      // ignore
    } finally {
      setReportLoading(false);
    }
  }

  async function submitFeedback() {
    if (!feedbackItemTarget) return;
    try {
      await fetch(`${API}/api/intelligence/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          answer_id: feedbackItemTarget.id,
          query: feedbackItemTarget.title,
          feedback_type: "citation_issue",
          notes: feedbackNotes,
        }),
      });
      setFeedbackSent(true);
      setTimeout(() => {
        setFeedbackOpen(false);
        setFeedbackSent(false);
        setFeedbackNotes("");
      }, 1500);
    } catch {
      // ignore
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#05070a] text-slate-100 font-sans">
      <Navbar />
      <div className="flex h-[calc(100vh-64px)] w-full flex-col overflow-hidden">
        {/* Top Intelligence Banner */}
        <div className="flex items-center justify-between border-b border-white/[0.08] bg-[#070b12]/90 px-4 py-2 backdrop-blur-md shrink-0">
          <div className="flex items-center gap-3">
            {/* Back to Dashboard Button */}
            <Link
              href="/"
              className="flex items-center gap-1.5 rounded-lg border border-white/[0.1] bg-white/[0.04] px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/[0.08] hover:text-white transition-all shadow-sm group"
              title="Return to Main Dakota Terminal & Overview"
            >
              <ArrowLeft className="h-3.5 w-3.5 text-cyan-400 group-hover:-translate-x-0.5 transition-transform" />
              <span>Back to Dashboard</span>
            </Link>

            <div className="h-4 w-px bg-white/[0.1] hidden sm:block" />

            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-tr from-cyan-600 to-indigo-600 shadow-lg shadow-cyan-500/20">
                <Cpu className="h-3.5 w-3.5 text-white" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold tracking-wider text-white">INTELLIGENCE CORE</span>
                  {systemStatus?.provider?.is_live ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[9px] font-mono font-bold text-emerald-400 border border-emerald-500/30">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      REAL AI ACTIVE
                    </span>
                  ) : (
                    <span className="rounded-full bg-cyan-500/10 px-2 py-0.5 text-[9px] font-mono font-semibold text-cyan-400 border border-cyan-500/20">
                      GROUNDED
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 text-[10px] text-slate-400 font-mono">
                  <span>
                    Provider:{" "}
                    <span className="text-cyan-300 font-medium">
                      {systemStatus?.provider?.provider === "mesh_api"
                        ? `Mesh API (${systemStatus?.provider?.model || "google/gemini-2.5-flash"})`
                        : systemStatus?.provider?.provider === "google_gemini"
                        ? `Google Gemini (${systemStatus?.provider?.model || "gemini-3.8-flash"})`
                        : "Grounded Synthesizer"}
                    </span>
                  </span>
                  <button
                    onClick={openDiagnostics}
                    className="inline-flex items-center gap-1 rounded border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-0.5 text-[9px] font-sans font-semibold text-cyan-300 hover:bg-cyan-500/20 transition-all cursor-pointer"
                    title="Inspect Mesh API & Gemini connection parameters"
                  >
                    <Activity className="h-2.5 w-2.5" />
                    Diagnostics / Check Mesh
                  </button>
                </div>
              </div>
            </div>
          </div>

        {/* View Switcher Tabs */}
        <div className="flex items-center gap-1 rounded-lg border border-white/[0.08] bg-black/40 p-1">
          <button
            onClick={() => setActiveTab("copilot")}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all ${
              activeTab === "copilot"
                ? "bg-cyan-500/20 text-cyan-300 shadow-sm border border-cyan-500/30"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Bot className="h-3.5 w-3.5" />
            AI Copilot
          </button>
          <button
            onClick={() => setActiveTab("search")}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all ${
              activeTab === "search"
                ? "bg-cyan-500/20 text-cyan-300 shadow-sm border border-cyan-500/30"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Search className="h-3.5 w-3.5" />
            Cross-Module Search
          </button>
          <button
            onClick={() => setActiveTab("report")}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all ${
              activeTab === "report"
                ? "bg-cyan-500/20 text-cyan-300 shadow-sm border border-cyan-500/30"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <FileText className="h-3.5 w-3.5" />
            Intelligence Reports
          </button>
        </div>

        {/* Quick Context Filter */}
        <div className="hidden sm:flex items-center gap-2 text-xs">
          <span className="text-slate-400">Focus Security:</span>
          <input
            type="text"
            placeholder="e.g. VARANIUM"
            value={activeTickerContext}
            onChange={(e) => setActiveTickerContext(e.target.value.toUpperCase())}
            className="w-28 rounded border border-white/10 bg-white/[0.03] px-2 py-0.5 font-mono text-xs text-white placeholder-slate-600 focus:border-cyan-500/50 focus:outline-none"
          />
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden">
        {/* ========================================================================= */}
        {/* TAB 1: COPILOT WORKBENCH */}
        {/* ========================================================================= */}
        {activeTab === "copilot" && (
          <div className="flex flex-1 overflow-hidden">
            {/* Sidebar: Conversation History & Prompts */}
            <div className="hidden md:flex w-72 flex-col border-r border-white/[0.08] bg-[#070b12]/50 p-3 shrink-0">
              <button
                onClick={startNewSession}
                className="flex items-center justify-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-300 transition-all hover:bg-cyan-500/20"
              >
                <Plus className="h-4 w-4" />
                New Investigation Session
              </button>

              <div className="mt-4 text-[11px] font-mono font-semibold text-slate-500 uppercase tracking-wider">
                Prior Sessions
              </div>
              <div className="mt-2 flex-1 overflow-y-auto space-y-1">
                {conversations.length === 0 ? (
                  <div className="text-center py-4 text-xs text-slate-600">No prior sessions</div>
                ) : (
                  conversations.map((c) => (
                    <div
                      key={c.id}
                      onClick={() => selectConversation(c.id)}
                      className={`group flex items-center justify-between rounded-md px-2.5 py-2 text-xs cursor-pointer transition-colors ${
                        currentConversationId === c.id
                          ? "bg-white/[0.08] text-white font-medium"
                          : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200"
                      }`}
                    >
                      <span className="truncate pr-2">{c.title || "Session"}</span>
                      <button
                        onClick={(e) => deleteSession(c.id, e)}
                        className="opacity-0 group-hover:opacity-100 hover:text-rose-400 p-0.5 transition-opacity"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  ))
                )}
              </div>

              {/* Sample Prompts */}
              <div className="mt-4 border-t border-white/[0.08] pt-3">
                <div className="text-[11px] font-mono font-semibold text-slate-500 uppercase tracking-wider mb-2">
                  Quick Inquiries
                </div>
                <div className="space-y-1.5">
                  {SAMPLE_PROMPTS.slice(0, 3).map((prompt, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSendMessage(prompt)}
                      className="w-full text-left rounded-md bg-white/[0.02] hover:bg-white/[0.05] p-2 text-[11px] text-slate-300 transition-colors line-clamp-2 border border-white/[0.04]"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Central Chat Thread */}
            <div className="flex flex-1 flex-col overflow-hidden bg-[#05070a]">
              {/* Message List */}
              <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
                {messages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full max-w-2xl mx-auto text-center px-4">
                    <div className="h-12 w-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mb-4 text-cyan-400">
                      <Sparkles className="h-6 w-6" />
                    </div>
                    <h2 className="text-lg font-bold text-white mb-2">Dakota Forensic Copilot</h2>
                    <p className="text-xs text-slate-400 mb-6 max-w-md">
                      Ask natural language questions grounded directly in Dakota's market data, 
                      regulatory risk engine, RSS news, and syndicate intake channels.
                    </p>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full text-left">
                      {SAMPLE_PROMPTS.map((prompt, i) => (
                        <button
                          key={i}
                          onClick={() => handleSendMessage(prompt)}
                          className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3 text-xs text-slate-300 hover:border-cyan-500/40 hover:bg-cyan-500/[0.04] transition-all group flex items-start justify-between"
                        >
                          <span>{prompt}</span>
                          <ChevronRight className="h-4 w-4 text-slate-600 group-hover:text-cyan-400 shrink-0 ml-2" />
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={`flex gap-3 max-w-4xl ${
                        msg.role === "user" ? "ml-auto justify-end" : "mr-auto justify-start"
                      }`}
                    >
                      {msg.role === "assistant" && (
                        <div className="h-8 w-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center shrink-0 text-cyan-400 mt-1">
                          <Bot className="h-4 w-4" />
                        </div>
                      )}

                      <div
                        className={`rounded-2xl p-4 sm:p-5 text-sm ${
                          msg.role === "user"
                            ? "bg-gradient-to-r from-cyan-600 to-indigo-600 text-white max-w-lg shadow-lg"
                            : "bg-[#0b1019] border border-white/[0.08] text-slate-200 w-full shadow-md"
                        }`}
                      >
                        {msg.role === "user" ? (
                          <div className="whitespace-pre-wrap">{msg.content}</div>
                        ) : (
                          <div>
                            {/* Assistant Header Actions */}
                            <div className="flex items-center justify-between border-b border-white/[0.06] pb-2 mb-3 text-xs text-slate-400">
                              <div className="flex items-center gap-2">
                                <span className="font-semibold text-cyan-400">Dakota Intelligence</span>
                                <span className="rounded bg-indigo-500/15 border border-indigo-500/25 px-1.5 py-0.5 text-[9px] text-indigo-300 font-mono">
                                  {systemStatus?.provider?.provider === "mesh_api"
                                    ? "via Mesh API"
                                    : systemStatus?.provider?.provider === "google_gemini"
                                    ? "via Gemini 3.8"
                                    : "via Grounded Core"}
                                </span>
                                {msg.confidence_score !== undefined && (
                                  <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-400 font-mono">
                                    {Math.round(msg.confidence_score * 100)}% Confidence
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={() => copyToClipboard(msg.content, msg.id)}
                                  className="hover:text-white flex items-center gap-1 text-[11px]"
                                >
                                  {copiedId === msg.id ? (
                                    <>
                                      <Check className="h-3 w-3 text-emerald-400" />
                                      <span className="text-emerald-400">Copied</span>
                                    </>
                                  ) : (
                                    <>
                                      <Copy className="h-3 w-3" />
                                      <span>Copy</span>
                                    </>
                                  )}
                                </button>
                                {msg.evidence && msg.evidence.length > 0 && (
                                  <button
                                    onClick={() => openInspectorWithEvidence(msg.evidence!)}
                                    className="flex items-center gap-1 text-[11px] text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20"
                                  >
                                    <Layers className="h-3 w-3" />
                                    <span>Inspect Evidence ({msg.evidence.length})</span>
                                  </button>
                                )}
                              </div>
                            </div>

                            {/* Contradictions Banner */}
                            {msg.contradictions && msg.contradictions.length > 0 && (
                              <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300 flex items-start gap-2">
                                <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
                                <div>
                                  <div className="font-semibold mb-0.5">Divergence / Contradiction Flagged</div>
                                  {msg.contradictions.map((c, i) => (
                                    <div key={i}>{c}</div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Content Body with Interactive Citations */}
                            <div className="prose prose-invert prose-sm max-w-none space-y-3 leading-relaxed">
                              {msg.content.split("\n\n").map((para, pIdx) => {
                                // Split on citation tags like [E1], [E2]
                                const parts = para.split(/(\[E\d+\])/g);
                                return (
                                  <p key={pIdx}>
                                    {parts.map((part, partIdx) => {
                                      if (/^\[E\d+\]$/.test(part)) {
                                        return (
                                          <button
                                            key={partIdx}
                                            onClick={() => handleCitationClick(part, msg.evidence)}
                                            className="inline-flex items-center rounded bg-cyan-500/20 px-1.5 py-0.2 mx-0.5 text-[11px] font-mono font-bold text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/30 cursor-pointer"
                                            title="Click to inspect this evidence item in detail"
                                          >
                                            {part}
                                          </button>
                                        );
                                      }
                                      return part;
                                    })}
                                  </p>
                                );
                              })}
                            </div>

                            {msg.isStreaming && (
                              <div className="inline-block h-3 w-1.5 bg-cyan-400 animate-pulse ml-1" />
                            )}

                            {/* Citations Footer Row */}
                            {msg.citations && msg.citations.length > 0 && (
                              <div className="mt-4 pt-3 border-t border-white/[0.06]">
                                <div className="text-[11px] font-mono text-slate-500 mb-2">
                                  VERIFIED CITATIONS & SOURCES:
                                </div>
                                <div className="flex flex-wrap gap-2">
                                  {msg.citations.map((c, cIdx) => (
                                    <div
                                      key={cIdx}
                                      className="inline-flex items-center gap-1 bg-white/[0.03] hover:bg-white/[0.08] px-2.5 py-1 rounded border border-white/[0.08] text-slate-300 transition-colors"
                                    >
                                      <button
                                        onClick={() => handleCitationClick(c.label, msg.evidence)}
                                        className="flex items-center gap-1.5 text-xs text-left cursor-pointer"
                                        title="Inspect in evidence drawer"
                                      >
                                        <span className="font-mono text-cyan-400 font-bold">{c.label}</span>
                                        <span className="truncate max-w-[170px]">{c.source_name}</span>
                                      </button>
                                      {c.source_url && (
                                        <Link
                                          href={c.source_url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="p-0.5 text-slate-400 hover:text-cyan-300 ml-0.5"
                                          title={`Redirect to source: ${c.source_url}`}
                                        >
                                          <ArrowUpRight className="h-3 w-3" />
                                        </Link>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Suggested Follow-ups */}
                            {msg.followups && msg.followups.length > 0 && !msg.isStreaming && (
                              <div className="mt-4 pt-2">
                                <div className="text-[11px] font-mono text-slate-500 mb-1.5">
                                  SUGGESTED INVESTIGATIVE STEPS:
                                </div>
                                <div className="flex flex-wrap gap-1.5">
                                  {msg.followups.map((f, fIdx) => (
                                    <button
                                      key={fIdx}
                                      onClick={() => handleSendMessage(f)}
                                      className="rounded-full border border-cyan-500/20 bg-cyan-500/5 px-2.5 py-1 text-xs text-cyan-300 hover:bg-cyan-500/15 transition-all text-left"
                                    >
                                      + {f}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Chat Input Bar */}
              <div className="border-t border-white/[0.08] bg-[#070b12] p-3 sm:p-4">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleSendMessage();
                  }}
                  className="flex items-center gap-2 max-w-4xl mx-auto rounded-xl border border-white/10 bg-white/[0.02] p-1.5 focus-within:border-cyan-500/50 focus-within:ring-1 focus-within:ring-cyan-500/30"
                >
                  <input
                    type="text"
                    value={inputQuery}
                    onChange={(e) => setInputQuery(e.target.value)}
                    placeholder="Ask Dakota Copilot: e.g. 'Investigate VARANIUM with news and risk score'..."
                    disabled={loading}
                    className="flex-1 bg-transparent px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={loading || !inputQuery.trim()}
                    className="flex h-9 w-9 items-center justify-center rounded-lg bg-cyan-600 text-white transition-all hover:bg-cyan-500 disabled:opacity-30 disabled:hover:bg-cyan-600"
                  >
                    {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </button>
                </form>
              </div>
            </div>

            {/* Evidence Inspector Side Panel */}
            {inspectorOpen && (
              <div className="w-96 border-l border-white/[0.08] bg-[#080d16] flex flex-col shrink-0 overflow-hidden shadow-2xl z-20">
                <div className="flex items-center justify-between border-b border-white/[0.08] p-3 bg-black/30">
                  <div className="flex items-center gap-2">
                    <Layers className="h-4 w-4 text-cyan-400" />
                    <span className="text-xs font-bold text-white tracking-wide">EVIDENCE INSPECTOR</span>
                  </div>
                  <button
                    onClick={() => setInspectorOpen(false)}
                    className="text-slate-400 hover:text-white p-1"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto p-3 space-y-3">
                  <div className="text-[11px] font-mono text-slate-400">
                    Showing {activeEvidenceList.length} verified records retrieved for this query.
                  </div>

                  {activeEvidenceList.map((item) => {
                    const isSelected = selectedEvidenceItem?.id === item.id;
                    return (
                      <div
                        key={item.id}
                        onClick={() => setSelectedEvidenceItem(item)}
                        className={`rounded-xl border p-3 text-xs transition-all cursor-pointer ${
                          isSelected
                            ? "border-cyan-500/60 bg-cyan-500/10 ring-1 ring-cyan-500/30"
                            : "border-white/[0.08] bg-white/[0.02] hover:bg-white/[0.05]"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="font-mono font-bold text-cyan-400 bg-cyan-500/20 px-1.5 py-0.5 rounded text-[10px]">
                            [{item.id}]
                          </span>
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold ${
                              item.observation_type === "directly_observed"
                                ? "bg-emerald-500/10 text-emerald-400"
                                : item.observation_type === "model_inferred"
                                ? "bg-amber-500/10 text-amber-400"
                                : "bg-rose-500/10 text-rose-400"
                            }`}
                          >
                            {item.observation_type.replace("_", " ").toUpperCase()}
                          </span>
                        </div>

                        <div className="font-semibold text-white mb-1">{item.title}</div>
                        <div className="text-slate-300 text-[11px] leading-relaxed mb-2 line-clamp-3">
                          {item.snippet}
                        </div>

                        <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 border-t border-white/[0.04] pt-2">
                          <span className="truncate max-w-[150px]">{item.source_name}</span>
                          <div className="flex items-center gap-2">
                            <span>Confidence: {Math.round(item.confidence * 100)}%</span>
                            {item.source_url && (
                              <Link
                                href={item.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="flex items-center gap-0.5 text-cyan-400 hover:text-cyan-300 font-sans ml-1"
                                title="Open source record in new tab"
                              >
                                <span>Source</span>
                                <ExternalLink className="h-2.5 w-2.5" />
                              </Link>
                            )}
                          </div>
                        </div>

                        {isSelected && (
                          <div className="mt-3 pt-2 border-t border-white/[0.08] flex items-center justify-between">
                            {item.source_url ? (
                              <Link
                                href={item.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-1 text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 hover:underline"
                              >
                                <span>Inspect Source</span>
                                <ExternalLink className="h-3 w-3" />
                              </Link>
                            ) : (
                              <span className="text-[10px] text-slate-500">Internal Record</span>
                            )}

                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setFeedbackItemTarget(item);
                                setFeedbackOpen(true);
                              }}
                              className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-amber-400"
                            >
                              <Flag className="h-3 w-3" />
                              <span>Flag / Feedback</span>
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: CROSS-MODULE SEARCH */}
        {/* ========================================================================= */}
        {activeTab === "search" && (
          <div className="flex-1 overflow-y-auto p-4 sm:p-8 max-w-5xl mx-auto w-full">
            <div className="mb-6">
              <h2 className="text-lg font-bold text-white mb-1">Cross-Module Intelligence Search</h2>
              <p className="text-xs text-slate-400">
                Unified search indexing across Stocks Screener, Live Forensic Wire, Syndicate Campaigns, and Portfolio Holdings.
              </p>
            </div>

            <form onSubmit={handleSearch} className="space-y-4 mb-8">
              <div className="flex items-center gap-2">
                <div className="flex-1 flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  <Search className="h-4 w-4 text-cyan-400 shrink-0" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search by ticker, company, keyword, or campaign channel (e.g. VARANIUM, TATA, @channel)..."
                    className="flex-1 bg-transparent text-sm text-white placeholder-slate-500 focus:outline-none"
                  />
                </div>
                <button
                  type="submit"
                  disabled={searchLoading}
                  className="rounded-xl bg-cyan-600 px-5 py-2 text-xs font-semibold text-white hover:bg-cyan-500 disabled:opacity-50"
                >
                  {searchLoading ? "Searching..." : "Search"}
                </button>
              </div>

              {/* Filters */}
              <div className="flex flex-wrap items-center gap-3 text-xs">
                <span className="text-slate-500 font-mono text-[11px]">MODULE:</span>
                {["", "stock", "investigation", "campaign", "portfolio"].map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => {
                      setSearchFilterType(t);
                      setTimeout(handleSearch, 50);
                    }}
                    className={`rounded-md px-2.5 py-1 transition-all ${
                      searchFilterType === t
                        ? "bg-cyan-500/20 text-cyan-300 font-semibold border border-cyan-500/30"
                        : "bg-white/[0.03] text-slate-400 hover:text-white"
                    }`}
                  >
                    {t ? t.toUpperCase() : "ALL MODULES"}
                  </button>
                ))}

                <span className="text-slate-500 font-mono text-[11px] ml-4">RISK BAND:</span>
                {["", "High", "Elevated", "Low"].map((b) => (
                  <button
                    key={b}
                    type="button"
                    onClick={() => {
                      setSearchBand(b);
                      setTimeout(handleSearch, 50);
                    }}
                    className={`rounded-md px-2.5 py-1 transition-all ${
                      searchBand === b
                        ? "bg-cyan-500/20 text-cyan-300 font-semibold border border-cyan-500/30"
                        : "bg-white/[0.03] text-slate-400 hover:text-white"
                    }`}
                  >
                    {b ? b : "ANY BAND"}
                  </button>
                ))}
              </div>
            </form>

            {/* Results */}
            <div className="space-y-3">
              {searchResults.length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-xs">
                  {searchLoading ? "Scanning all Dakota records..." : "Enter a search query to search across modules."}
                </div>
              ) : (
                searchResults.map((r) => (
                  <div
                    key={r.id}
                    className="rounded-xl border border-white/[0.08] bg-[#080d16] p-4 text-xs transition-all hover:border-cyan-500/30"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-cyan-500/10 px-2 py-0.5 font-mono text-[10px] font-bold text-cyan-400 border border-cyan-500/20">
                          {r.type.toUpperCase()}
                        </span>
                        <span className="font-semibold text-white text-sm">{r.title}</span>
                      </div>
                      {r.band && (
                        <span
                          className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold ${
                            r.band === "High"
                              ? "bg-rose-500/10 text-rose-400"
                              : r.band === "Elevated"
                              ? "bg-amber-500/10 text-amber-400"
                              : "bg-emerald-500/10 text-emerald-400"
                          }`}
                        >
                          {r.score !== null ? `${r.score}/100 — ` : ""}
                          {r.band} Risk
                        </span>
                      )}
                    </div>

                    <div className="text-slate-400 mb-1">{r.subtitle}</div>
                    <div className="text-slate-300 text-xs mb-3">{r.snippet}</div>

                    {r.url && (
                      <Link
                        href={r.url}
                        className="inline-flex items-center gap-1 text-cyan-400 hover:underline text-xs"
                      >
                        <span>Open in {r.type} module</span>
                        <ArrowUpRight className="h-3 w-3" />
                      </Link>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: INTELLIGENCE REPORTS GENERATOR */}
        {/* ========================================================================= */}
        {activeTab === "report" && (
          <div className="flex-1 overflow-y-auto p-4 sm:p-8 max-w-5xl mx-auto w-full">
            <div className="mb-6">
              <h2 className="text-lg font-bold text-white mb-1">Automated Intelligence Reports</h2>
              <p className="text-xs text-slate-400">
                Compile grounded executive briefs, evidence chronologies, and risk assessments with verifiable source lists.
              </p>
            </div>

            {/* Generator Form */}
            <div className="rounded-2xl border border-white/10 bg-[#080d16] p-5 mb-8">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1">TARGET TICKER / ENTITY</label>
                  <input
                    type="text"
                    value={reportTicker}
                    onChange={(e) => setReportTicker(e.target.value.toUpperCase())}
                    className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-mono text-slate-400 mb-1">REPORT TYPE</label>
                  <select
                    value={reportType}
                    onChange={(e) => setReportType(e.target.value)}
                    className="w-full rounded-lg border border-white/10 bg-[#070b12] px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
                  >
                    <option value="company_brief">Company Intelligence Brief</option>
                    <option value="market_news">Market & News Analysis</option>
                    <option value="investigation_summary">Investigation Summary</option>
                    <option value="risk_assessment">Risk Assessment Summary</option>
                  </select>
                </div>

                <div className="flex items-end">
                  <button
                    onClick={handleGenerateReport}
                    disabled={reportLoading}
                    className="w-full rounded-lg bg-gradient-to-r from-cyan-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 transition-all shadow-lg shadow-cyan-500/20"
                  >
                    {reportLoading ? "Synthesizing Brief..." : "Compile Report"}
                  </button>
                </div>
              </div>
            </div>

            {/* Report Viewer */}
            {generatedReport && (
              <div className="rounded-2xl border border-white/10 bg-[#080d16] p-6 shadow-xl">
                <div className="flex items-center justify-between border-b border-white/10 pb-4 mb-6">
                  <div>
                    <h3 className="text-base font-bold text-white">{generatedReport.report.title}</h3>
                    <div className="text-xs text-slate-400 font-mono mt-0.5">
                      ID: {generatedReport.report.id} | Generated: {generatedReport.report.generated_at?.slice(0, 16)} UTC
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        const blob = new Blob([generatedReport.markdown], { type: "text/markdown" });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = `${generatedReport.report.id}.md`;
                        a.click();
                      }}
                      className="flex items-center gap-1 rounded border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-slate-300 hover:bg-white/[0.08]"
                    >
                      <Download className="h-3.5 w-3.5" />
                      Download .MD
                    </button>
                    <button
                      onClick={() => {
                        const win = window.open("", "_blank");
                        if (win) {
                          win.document.write(generatedReport.html);
                          win.document.close();
                          win.print();
                        }
                      }}
                      className="flex items-center gap-1 rounded border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-300 hover:bg-cyan-500/20"
                    >
                      <Printer className="h-3.5 w-3.5" />
                      Print / PDF
                    </button>
                  </div>
                </div>

                {/* Report Sections */}
                <div className="space-y-6 text-sm text-slate-200">
                  <div>
                    <h4 className="text-xs font-mono font-bold text-cyan-400 uppercase tracking-wider mb-2">
                      1. Executive Summary
                    </h4>
                    <p className="leading-relaxed bg-white/[0.02] p-3 rounded-lg border border-white/[0.04]">
                      {generatedReport.report.executive_summary}
                    </p>
                  </div>

                  <div>
                    <h4 className="text-xs font-mono font-bold text-cyan-400 uppercase tracking-wider mb-2">
                      2. Scope & Methodology
                    </h4>
                    <p className="text-xs text-slate-400">{generatedReport.report.scope_and_methodology}</p>
                  </div>

                  <div>
                    <h4 className="text-xs font-mono font-bold text-cyan-400 uppercase tracking-wider mb-2">
                      3. Key Verified Findings
                    </h4>
                    <div className="space-y-2">
                      {generatedReport.report.key_findings.map((f: any, i: number) => (
                        <div key={i} className="flex items-start gap-2 bg-white/[0.02] p-2.5 rounded-lg border border-white/[0.04]">
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-mono font-bold ${
                              f.severity === "high"
                                ? "bg-rose-500/10 text-rose-400"
                                : "bg-emerald-500/10 text-emerald-400"
                            }`}
                          >
                            {f.severity.toUpperCase()}
                          </span>
                          <span className="text-xs">{f.claim}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Sources Provenance */}
                  <div>
                    <h4 className="text-xs font-mono font-bold text-cyan-400 uppercase tracking-wider mb-2">
                      4. Source Provenance Table
                    </h4>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs border border-white/10 rounded-lg overflow-hidden">
                        <thead className="bg-white/[0.05] text-slate-400 font-mono text-[11px]">
                          <tr>
                            <th className="p-2">ID</th>
                            <th className="p-2">Source Name</th>
                            <th className="p-2">Type</th>
                            <th className="p-2">Confidence</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.06]">
                          {generatedReport.report.source_list.map((s: any, idx: number) => (
                            <tr key={idx} className="hover:bg-white/[0.02]">
                              <td className="p-2 font-mono text-cyan-400">[{s.id}]</td>
                              <td className="p-2">{s.name}</td>
                              <td className="p-2 uppercase text-slate-400">{s.type}</td>
                              <td className="p-2 font-mono">{Math.round(s.confidence * 100)}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-3 text-xs text-rose-300">
                    <strong>Regulatory Disclaimer:</strong> Dakota reports available risk indicators only. Not investment advice, not an accusation of fraud.
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Flag / Feedback Modal */}
      {feedbackOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-white/15 bg-[#0b1019] p-5 shadow-2xl">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2 text-white font-bold text-sm">
                <Flag className="h-4 w-4 text-amber-400" />
                <span>Flag Citation or Evidence</span>
              </div>
              <button onClick={() => setFeedbackOpen(false)} className="text-slate-400 hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>

            {feedbackSent ? (
              <div className="py-6 text-center text-emerald-400 text-xs font-semibold">
                ✓ Feedback recorded. Thank you for helping keep Dakota grounded!
              </div>
            ) : (
              <div>
                <p className="text-xs text-slate-400 mb-3">
                  Flag an inaccurate excerpt, broken citation link, or conflicting reporting for audit:
                </p>
                <div className="p-2 bg-white/[0.03] rounded border border-white/[0.06] text-xs text-slate-300 font-mono mb-3">
                  [{feedbackItemTarget?.id}] {feedbackItemTarget?.source_name}
                </div>
                <textarea
                  value={feedbackNotes}
                  onChange={(e) => setFeedbackNotes(e.target.value)}
                  placeholder="Describe the discrepancy or error..."
                  className="w-full h-24 rounded-lg border border-white/10 bg-white/[0.02] p-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 mb-4"
                />
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setFeedbackOpen(false)}
                    className="rounded px-3 py-1.5 text-xs text-slate-400 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={submitFeedback}
                    className="rounded bg-amber-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-amber-500"
                  >
                    Submit Flag
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* AI Provider & Mesh Diagnostics Modal */}
      {diagOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
          <div className="w-full max-w-lg rounded-2xl border border-white/15 bg-[#0b1019] p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-4 border-b border-white/[0.08] pb-3">
              <div className="flex items-center gap-2.5 text-white font-bold text-sm">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                  <Activity className="h-4 w-4" />
                </div>
                <div>
                  <div className="text-sm font-bold text-white">AI Provider & Mesh API Diagnostics</div>
                  <div className="text-[11px] font-normal text-slate-400 font-mono">
                    Live connection status & verification
                  </div>
                </div>
              </div>
              <button onClick={() => setDiagOpen(false)} className="text-slate-400 hover:text-white p-1">
                <X className="h-5 w-5" />
              </button>
            </div>

            {diagLoading ? (
              <div className="py-12 flex flex-col items-center justify-center gap-3">
                <RefreshCw className="h-6 w-6 animate-spin text-cyan-400" />
                <span className="text-xs text-slate-400">Pinging Mesh API and Google Gemini endpoints...</span>
              </div>
            ) : diagData ? (
              <div className="space-y-4">
                {/* Mesh API Card */}
                <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-xs text-white">Mesh API Router (meshapi.ai)</span>
                      {diagData.mesh_api?.authenticated ? (
                        <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-mono font-bold text-emerald-400">
                          AUTHENTICATED 200 OK
                        </span>
                      ) : (
                        <span className="rounded-full bg-rose-500/15 border border-rose-500/30 px-2 py-0.5 text-[10px] font-mono font-bold text-rose-400">
                          NOT CONNECTED
                        </span>
                      )}
                    </div>
                    {diagData.mesh_api?.latency_ms && (
                      <span className="text-[10px] font-mono text-cyan-400">
                        {diagData.mesh_api.latency_ms}ms ping
                      </span>
                    )}
                  </div>

                  <div className="space-y-1.5 text-xs text-slate-300">
                    <div className="flex justify-between text-[11px]">
                      <span className="text-slate-400">Configured Key:</span>
                      <span className="font-mono text-cyan-300">{diagData.mesh_api?.key_masked || "Not set in .env"}</span>
                    </div>
                    <div className="flex justify-between text-[11px]">
                      <span className="text-slate-400">Router Endpoint:</span>
                      <span className="font-mono text-slate-300">{diagData.mesh_api?.base_url}</span>
                    </div>
                    <div className="flex justify-between text-[11px]">
                      <span className="text-slate-400">Active Model:</span>
                      <span className="font-mono text-slate-300">{diagData.mesh_api?.model}</span>
                    </div>
                  </div>

                  {/* Operational Status / Note */}
                  <div className={`mt-3 rounded-lg p-2.5 text-xs ${
                    diagData.mesh_api?.chat_operational
                      ? "bg-emerald-500/10 border border-emerald-500/30 text-emerald-300"
                      : "bg-amber-500/10 border border-amber-500/30 text-amber-300"
                  }`}>
                    {diagData.mesh_api?.status_note}
                  </div>
                </div>

                {/* Secondary Provider: Google Gemini */}
                <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-xs text-white">Google Gemini</span>
                      {diagData.google_gemini?.operational ? (
                        <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-mono font-bold text-emerald-400">
                          LIVE & ACTIVE
                        </span>
                      ) : (
                        <span className="rounded-full bg-slate-500/15 border border-white/10 px-2 py-0.5 text-[10px] font-mono text-slate-400">
                          FALLBACK READY
                        </span>
                      )}
                    </div>
                    {diagData.google_gemini?.latency_ms && (
                      <span className="text-[10px] font-mono text-cyan-400">
                        {diagData.google_gemini.latency_ms}ms
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-slate-400">
                    Model: <span className="text-slate-200 font-mono">{diagData.google_gemini?.model}</span>
                  </div>
                  <div className="text-[11px] text-slate-300 mt-1">
                    Status: {diagData.google_gemini?.status_note}
                  </div>
                </div>

                {/* Active Routing Verdict */}
                <div className="rounded-lg bg-indigo-500/10 border border-indigo-500/30 p-3 text-xs text-indigo-200">
                  <div className="font-semibold mb-1 flex items-center gap-1.5">
                    <Zap className="h-3.5 w-3.5 text-indigo-400" />
                    Automatic Failover Protection:
                  </div>
                  <p className="text-[11px] text-indigo-200/90 leading-relaxed">
                    Dakota connects directly to Mesh API with your verified key. If Mesh has balance, queries route through Mesh. If balance is 0 or needs top-up on app.meshapi.ai, Dakota automatically routes through Google Gemini so your workflow is never blocked.
                  </p>
                </div>

                <div className="flex justify-between items-center pt-2">
                  <button
                    onClick={openDiagnostics}
                    className="flex items-center gap-1.5 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    Re-Test Ping
                  </button>
                  <button
                    onClick={() => setDiagOpen(false)}
                    className="rounded-lg bg-white/10 px-4 py-1.5 text-xs font-semibold text-white hover:bg-white/15"
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
