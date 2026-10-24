"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  RefreshCw,
  ExternalLink,
  ShieldAlert,
  TrendingUp,
  AlertTriangle,
  Link2,
  MessageSquare,
  Users,
  FileText,
  Layers,
  Sparkles,
  Info,
  CheckCircle2,
  AlertOctagon
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type GraphNode = {
  id: string;
  type: "campaign" | "security" | "actor" | "message" | "alert" | "url" | "disclosure";
  label: string;
  sublabel?: string | null;
  status?: string | null;
  properties?: Record<string, any>;
  evidence_ids?: string[];
  x?: number;
  y?: number;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  label: string;
  rationale: string;
  confidence?: number;
  evidence_references?: string[];
  properties?: Record<string, any>;
};

export type CampaignGraphData = {
  campaign_id: string;
  name: string;
  tier: "HIGH" | "MODERATE" | "CANDIDATE";
  status: string;
  confidence_score: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  metrics: Record<string, any>;
  contradictions?: string[];
  missing_evidence?: string[];
  disclaimer?: string;
};

type Props = {
  campaignId: string;
  onSelectTicker?: (ticker: string) => void;
};

export default function CampaignGraph({ campaignId, onSelectTicker }: Props) {
  const [data, setData] = useState<CampaignGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState<"canvas" | "list">("canvas");

  // Interaction state
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);

  // Pan & Zoom
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let isMounted = true;
    async function fetchGraph() {
      setLoading(true);
      setError("");
      try {
        const res = await fetch(`${API}/api/campaigns/${campaignId}/graph`);
        if (!res.ok) throw new Error("Could not load campaign relationship graph");
        const json = await res.json();
        if (isMounted) {
          setData(json);
          // Set central campaign node as initial selection
          const cmpNode = json.nodes?.find((n: GraphNode) => n.type === "campaign");
          if (cmpNode) setSelectedNode(cmpNode);
        }
      } catch (err) {
        if (isMounted) setError(err instanceof Error ? err.message : "Failed to load graph");
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    fetchGraph();
    return () => {
      isMounted = false;
    };
  }, [campaignId]);

  // Deterministic concentric radial layout calculation
  const layoutNodes = useMemo(() => {
    if (!data || !data.nodes.length) return [];
    const width = 800;
    const height = 540;
    const cx = width / 2;
    const cy = height / 2;

    const nodes = [...data.nodes];
    const securities = nodes.filter((n) => n.type === "security");
    const actors = nodes.filter((n) => n.type === "actor");
    const alerts = nodes.filter((n) => n.type === "alert");
    const urls = nodes.filter((n) => n.type === "url");
    const messages = nodes.filter((n) => n.type === "message");
    const others = nodes.filter(
      (n) => !["campaign", "security", "actor", "alert", "url", "message"].includes(n.type)
    );

    const positions: Record<string, { x: number; y: number }> = {};

    // Center: Campaign Node
    const cmp = nodes.find((n) => n.type === "campaign");
    if (cmp) positions[cmp.id] = { x: cx, y: cy };

    // Ring 1 (Radius 120): Securities
    const r1 = 125;
    securities.forEach((sec, idx) => {
      const angle = (2 * Math.PI * idx) / Math.max(1, securities.length) - Math.PI / 2;
      positions[sec.id] = {
        x: cx + r1 * Math.cos(angle),
        y: cy + r1 * Math.sin(angle),
      };
    });

    // Ring 2 (Radius 200): Promoters / Actors and Alerts
    const r2 = 205;
    const ring2Items = [...actors, ...alerts];
    ring2Items.forEach((item, idx) => {
      const angle = (2 * Math.PI * idx) / Math.max(1, ring2Items.length) - Math.PI / 4;
      positions[item.id] = {
        x: cx + r2 * Math.cos(angle),
        y: cy + r2 * Math.sin(angle),
      };
    });

    // Ring 3 (Radius 260): URLs, Messages, Disclosures
    const r3 = 265;
    const ring3Items = [...urls, ...messages, ...others];
    ring3Items.forEach((item, idx) => {
      const angle = (2 * Math.PI * idx) / Math.max(1, ring3Items.length);
      positions[item.id] = {
        x: cx + r3 * Math.cos(angle),
        y: cy + r3 * Math.sin(angle),
      };
    });

    return nodes.map((n) => ({
      ...n,
      x: positions[n.id]?.x ?? cx,
      y: positions[n.id]?.y ?? cy,
    }));
  }, [data]);

  const nodeMap = useMemo(() => {
    const map = new Map<string, GraphNode>();
    layoutNodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [layoutNodes]);

  // Mouse pan handlers
  function handleMouseDown(e: React.MouseEvent) {
    if (e.button !== 0) return; // left click only
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  }

  function handleMouseMove(e: React.MouseEvent) {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  }

  function handleMouseUp() {
    setIsDragging(false);
  }

  function handleWheel(e: React.WheelEvent) {
    e.preventDefault();
    const zoomDelta = e.deltaY < 0 ? 0.1 : -0.1;
    setZoom((prev) => Math.min(2.5, Math.max(0.4, prev + zoomDelta)));
  }

  function resetView() {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }

  // Node styling helpers
  function getNodeColor(type: string) {
    switch (type) {
      case "campaign":
        return { fill: "#581c87", stroke: "#c084fc", text: "#f3e8ff", glow: "rgba(192, 132, 252, 0.4)" };
      case "security":
        return { fill: "#083344", stroke: "#22d3ee", text: "#cffafe", glow: "rgba(34, 211, 238, 0.4)" };
      case "actor":
        return { fill: "#451a03", stroke: "#fbbf24", text: "#fef3c7", glow: "rgba(251, 191, 36, 0.4)" };
      case "alert":
        return { fill: "#4c0519", stroke: "#f43f5e", text: "#ffe4e6", glow: "rgba(244, 63, 94, 0.4)" };
      case "url":
        return { fill: "#172554", stroke: "#60a5fa", text: "#dbeafe", glow: "rgba(96, 165, 250, 0.4)" };
      case "message":
        return { fill: "#0f172a", stroke: "#94a3b8", text: "#f1f5f9", glow: "rgba(148, 163, 184, 0.3)" };
      case "disclosure":
        return { fill: "#064e3b", stroke: "#34d399", text: "#d1fae5", glow: "rgba(52, 211, 153, 0.4)" };
      default:
        return { fill: "#1e293b", stroke: "#64748b", text: "#f8fafc", glow: "rgba(100, 116, 139, 0.3)" };
    }
  }

  function getEdgeColor(type: string) {
    switch (type) {
      case "promoted_by":
        return { stroke: "#fbbf24", strokeWidth: 2, strokeDasharray: "none" };
      case "market_corroboration":
        return { stroke: "#f43f5e", strokeWidth: 2.5, strokeDasharray: "none" };
      case "shared_template":
        return { stroke: "#22d3ee", strokeWidth: 1.8, strokeDasharray: "4 3" };
      case "shared_url":
        return { stroke: "#60a5fa", strokeWidth: 1.8, strokeDasharray: "none" };
      case "temporal_burst":
        return { stroke: "#a855f7", strokeWidth: 1.5, strokeDasharray: "2 2" };
      case "contradicted_by":
        return { stroke: "#ea580c", strokeWidth: 2, strokeDasharray: "5 3" };
      default:
        return { stroke: "#475569", strokeWidth: 1.2, strokeDasharray: "none" };
    }
  }

  if (loading) {
    return (
      <div className="py-16 text-center text-slate-500 font-mono text-xs">
        <RefreshCw className="h-6 w-6 animate-spin mx-auto text-cyan-400 mb-2" />
        Generating interactive syndicate relationship graph...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-white/[0.08] bg-slate-900/30 p-8 text-center">
        <AlertTriangle className="h-8 w-8 text-amber-500 mx-auto mb-2" />
        <div className="text-xs font-mono text-slate-300">{error || "No graph data available"}</div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/[0.1] bg-[#070b12] p-4 flex flex-col">
      {/* Graph Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.08] pb-3 mb-3">
        <div className="flex items-center gap-2">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-purple-950/40 border border-purple-500/30 text-[11px] font-mono text-purple-300">
            <Layers className="h-3 w-3" />
            <span>SYNDICATE GRAPH</span>
          </div>
          <span className="text-xs font-mono text-slate-400">
            {data.nodes.length} Nodes • {data.edges.length} Evidence Relationships
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Mode switch */}
          <div className="inline-flex rounded-lg bg-slate-900 p-0.5 border border-white/[0.08]">
            <button
              onClick={() => setViewMode("canvas")}
              className={`px-2.5 py-1 text-xs font-mono rounded-md transition-colors ${
                viewMode === "canvas" ? "bg-cyan-500/20 text-cyan-300" : "text-slate-400 hover:text-white"
              }`}
            >
              Graph Canvas
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={`px-2.5 py-1 text-xs font-mono rounded-md transition-colors ${
                viewMode === "list" ? "bg-cyan-500/20 text-cyan-300" : "text-slate-400 hover:text-white"
              }`}
            >
              Relationship List
            </button>
          </div>

          {/* Zoom controls (only in canvas mode) */}
          {viewMode === "canvas" && (
            <div className="flex items-center gap-1 bg-slate-900/80 border border-white/[0.08] rounded-lg p-0.5">
              <button
                onClick={() => setZoom((z) => Math.min(2.5, z + 0.15))}
                title="Zoom In"
                className="p-1 text-slate-400 hover:text-white rounded hover:bg-white/[0.05]"
              >
                <ZoomIn className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setZoom((z) => Math.max(0.4, z - 0.15))}
                title="Zoom Out"
                className="p-1 text-slate-400 hover:text-white rounded hover:bg-white/[0.05]"
              >
                <ZoomOut className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={resetView}
                title="Reset View"
                className="p-1 text-slate-400 hover:text-white rounded hover:bg-white/[0.05]"
              >
                <Maximize2 className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Main View Area */}
      {viewMode === "canvas" ? (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          {/* SVG Canvas Area (3 cols) */}
          <div
            ref={containerRef}
            className="lg:col-span-3 relative h-[520px] rounded-xl border border-white/[0.06] bg-[#03060a] overflow-hidden cursor-grab active:cursor-grabbing select-none"
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onWheel={handleWheel}
          >
            {/* Visual Legend */}
            <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-2 text-[10px] font-mono bg-black/60 backdrop-blur-md p-2 rounded-lg border border-white/[0.06]">
              <span className="flex items-center gap-1 text-purple-300">
                <span className="h-2 w-2 rounded-full bg-purple-500" /> Campaign
              </span>
              <span className="flex items-center gap-1 text-cyan-300">
                <span className="h-2 w-2 rounded-full bg-cyan-400" /> Security
              </span>
              <span className="flex items-center gap-1 text-amber-300">
                <span className="h-2 w-2 rounded-full bg-amber-400" /> Promoter
              </span>
              <span className="flex items-center gap-1 text-rose-300">
                <span className="h-2 w-2 rounded-full bg-rose-500" /> Alert
              </span>
              <span className="flex items-center gap-1 text-blue-300">
                <span className="h-2 w-2 rounded-full bg-blue-400" /> URL
              </span>
              <span className="flex items-center gap-1 text-slate-300">
                <span className="h-2 w-2 rounded-full bg-slate-400" /> Tip
              </span>
            </div>

            <svg
              className="w-full h-full"
              viewBox="0 0 800 540"
              preserveAspectRatio="xMidYMid meet"
            >
              <defs>
                <filter id="glow-cyan" x="-20%" y="-20%" width="140%" height="140%">
                  <feDropShadow dx="0" dy="0" stdDeviation="3" floodColor="#22d3ee" floodOpacity="0.4" />
                </filter>
                <filter id="glow-rose" x="-20%" y="-20%" width="140%" height="140%">
                  <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor="#f43f5e" floodOpacity="0.5" />
                </filter>
              </defs>

              <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
                {/* 1. EDGES */}
                {data.edges.map((edge) => {
                  const s = nodeMap.get(edge.source);
                  const t = nodeMap.get(edge.target);
                  if (!s || !t || s.x === undefined || s.y === undefined || t.x === undefined || t.y === undefined) return null;

                  const isSelected = selectedEdge?.id === edge.id;
                  const edgeStyle = getEdgeColor(edge.type);

                  return (
                    <g key={edge.id} className="cursor-pointer" onClick={(e) => { e.stopPropagation(); setSelectedEdge(edge); setSelectedNode(null); }}>
                      <line
                        x1={s.x}
                        y1={s.y}
                        x2={t.x}
                        y2={t.y}
                        stroke={isSelected ? "#38bdf8" : edgeStyle.stroke}
                        strokeWidth={isSelected ? edgeStyle.strokeWidth + 2 : edgeStyle.strokeWidth}
                        strokeDasharray={edgeStyle.strokeDasharray}
                        opacity={isSelected ? 1 : 0.65}
                      />
                    </g>
                  );
                })}

                {/* 2. NODES */}
                {layoutNodes.map((node) => {
                  if (node.x === undefined || node.y === undefined) return null;
                  const isSelected = selectedNode?.id === node.id;
                  const color = getNodeColor(node.type);
                  const isCmp = node.type === "campaign";
                  const isSec = node.type === "security";
                  const radius = isCmp ? 24 : isSec ? 18 : 14;

                  return (
                    <g
                      key={node.id}
                      className="cursor-pointer transition-transform"
                      transform={`translate(${node.x}, ${node.y})`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedNode(node);
                        setSelectedEdge(null);
                      }}
                    >
                      {/* Selection halo */}
                      {isSelected && (
                        <circle
                          r={radius + 6}
                          fill="none"
                          stroke="#38bdf8"
                          strokeWidth="2"
                          strokeDasharray="4 2"
                          className="animate-spin"
                        />
                      )}

                      {/* Node circle */}
                      <circle
                        r={radius}
                        fill={color.fill}
                        stroke={isSelected ? "#ffffff" : color.stroke}
                        strokeWidth={isSelected ? 2.5 : 1.5}
                      />

                      {/* Inner text symbol */}
                      <text
                        textAnchor="middle"
                        dy=".3em"
                        fontSize={isCmp ? 10 : isSec ? 9 : 8}
                        fontFamily="monospace"
                        fontWeight="bold"
                        fill={color.text}
                        pointerEvents="none"
                      >
                        {isCmp ? "CMP" : isSec ? node.label.slice(0, 4) : node.type[0].toUpperCase()}
                      </text>

                      {/* Sub-label text */}
                      <text
                        textAnchor="middle"
                        y={radius + 12}
                        fontSize="8.5"
                        fontFamily="monospace"
                        fill={isSelected ? "#38bdf8" : "#94a3b8"}
                        pointerEvents="none"
                        className="font-medium"
                      >
                        {node.label.length > 18 ? node.label.slice(0, 16) + "..." : node.label}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          </div>

          {/* Inspection Sidebar (1 col) */}
          <div className="lg:col-span-1 rounded-xl border border-white/[0.06] bg-slate-900/60 p-4 flex flex-col justify-between">
            {selectedNode ? (
              <div className="space-y-3">
                <div className="border-b border-white/[0.08] pb-2">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-cyan-400">
                    [{selectedNode.type}] Node Inspector
                  </span>
                  <h4 className="text-base font-bold text-white mt-1 break-words">
                    {selectedNode.label}
                  </h4>
                  {selectedNode.sublabel && (
                    <div className="text-xs font-mono text-slate-400">{selectedNode.sublabel}</div>
                  )}
                </div>

                {/* Node Properties */}
                <div className="space-y-1.5 text-xs font-mono text-slate-300">
                  {selectedNode.properties &&
                    Object.entries(selectedNode.properties).map(([k, v]) => {
                      if (v === null || v === undefined) return null;
                      return (
                        <div key={k} className="flex justify-between gap-2 border-b border-white/[0.03] py-0.5">
                          <span className="text-slate-500 uppercase text-[10px]">{k.replace("_", " ")}:</span>
                          <span className="text-slate-200 text-right truncate max-w-[140px]">{String(v)}</span>
                        </div>
                      );
                    })}
                </div>

                {/* Direct Action Link */}
                {selectedNode.type === "security" && (
                  <div className="pt-2 flex flex-col gap-2">
                    <Link
                      href={`/stocks/${selectedNode.label}`}
                      className="inline-flex items-center justify-center gap-1.5 w-full py-1.5 px-3 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-xs font-mono font-bold text-cyan-300"
                    >
                      <span>View Stock Page</span>
                      <ExternalLink className="h-3 w-3" />
                    </Link>
                    <Link
                      href={`/investigate?ticker=${selectedNode.label}`}
                      className="inline-flex items-center justify-center gap-1.5 w-full py-1.5 px-3 rounded-lg bg-purple-950/50 hover:bg-purple-900/60 border border-purple-500/40 text-xs font-mono font-bold text-purple-300"
                    >
                      <TrendingUp className="h-3 w-3" />
                      <span>Deep Forensic Dive</span>
                    </Link>
                  </div>
                )}
              </div>
            ) : selectedEdge ? (
              <div className="space-y-3">
                <div className="border-b border-white/[0.08] pb-2">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-amber-400">
                    [{selectedEdge.type}] Relationship
                  </span>
                  <h4 className="text-sm font-bold text-white mt-1">
                    {selectedEdge.label}
                  </h4>
                </div>

                <div className="text-xs text-slate-300 bg-black/40 p-2.5 rounded-lg border border-white/[0.05]">
                  <span className="font-mono text-cyan-300 font-semibold block mb-1">Correlation Rationale:</span>
                  <p>{selectedEdge.rationale}</p>
                </div>

                {selectedEdge.evidence_references && selectedEdge.evidence_references.length > 0 && (
                  <div>
                    <span className="text-[10px] font-mono uppercase text-slate-400 block mb-1">
                      Cited Evidence Tokens:
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {selectedEdge.evidence_references.map((evRef, i) => (
                        <span key={i} className="text-[10px] font-mono bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded truncate max-w-[200px]">
                          {evRef}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12 text-slate-500 font-mono text-xs">
                <Info className="h-6 w-6 mx-auto mb-2 text-slate-600" />
                Select any node or connecting edge in the graph to inspect evidence citations and forensic rationales.
              </div>
            )}

            {/* Missing Evidence / Disclaimer Footer */}
            <div className="pt-3 border-t border-white/[0.06] text-[10px] font-mono text-slate-400 space-y-1">
              {data.missing_evidence?.slice(0, 2).map((m, i) => (
                <div key={i} className="flex items-start gap-1 text-amber-400/80">
                  <AlertOctagon className="h-3 w-3 flex-shrink-0 mt-0.5" />
                  <span>{m}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* ACCESSIBLE RELATIONSHIP TABLE VIEW */
        <div className="rounded-xl border border-white/[0.06] bg-[#03060a] overflow-x-auto max-h-[500px]">
          <table className="w-full text-left border-collapse text-xs font-mono">
            <thead>
              <tr className="border-b border-white/[0.08] bg-slate-900/80 text-slate-400 text-[10px] uppercase">
                <th className="p-3">Source Node</th>
                <th className="p-3">Relationship Type</th>
                <th className="p-3">Target Node</th>
                <th className="p-3">Correlation Rationale</th>
                <th className="p-3">Evidence References</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {data.edges.map((e) => {
                const s = nodeMap.get(e.source);
                const t = nodeMap.get(e.target);
                return (
                  <tr key={e.id} className="hover:bg-slate-900/40 transition-colors">
                    <td className="p-3 text-cyan-300 font-bold">{s?.label || e.source}</td>
                    <td className="p-3 text-amber-300 uppercase text-[11px]">{e.label}</td>
                    <td className="p-3 text-slate-200">{t?.label || e.target}</td>
                    <td className="p-3 text-slate-400 max-w-xs">{e.rationale}</td>
                    <td className="p-3 text-slate-500 text-[10px]">
                      {e.evidence_references?.join(", ") || "Derived relation"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
