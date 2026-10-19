"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  ShieldAlert, 
  TrendingUp, 
  Briefcase, 
  Radio, 
  Users, 
  Eye, 
  Search, 
  Menu, 
  X,
  Activity,
  ChevronRight,
  Sparkles,
  Bell,
} from "lucide-react";
import CommandPalette from "./CommandPalette";

const NAV_LINKS = [
  { label: "Overview", href: "/", icon: ShieldAlert, badge: null },
  { label: "AI Copilot", href: "/intelligence", icon: Sparkles, badge: "CORE" },
  { label: "Stocks Screener", href: "/stocks", icon: TrendingUp, badge: "2.6K" },
  { label: "Portfolio", href: "/portfolio", icon: Briefcase, badge: null },
  { label: "Forensic Wire", href: "/investigate", icon: Radio, badge: "LIVE" },
  { label: "Syndicate Campaigns", href: "/campaigns", icon: Users, badge: "CARTEL" },
  { label: "Watcher Radar", href: "/watcher", icon: Eye, badge: null },
];

function NavbarInner() {
  const pathname = usePathname();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [timeStr, setTimeStr] = useState("");
  const [marketStatus, setMarketStatus] = useState("NSE/BSE CLOSED");

  // Real-time IST Clock & Market Status
  useEffect(() => {
    function updateClock() {
      const now = new Date();
      // IST is UTC+5:30
      const utc = now.getTime() + now.getTimezoneOffset() * 60000;
      const istDate = new Date(utc + 3600000 * 5.5);
      
      const hours = istDate.getHours();
      const minutes = istDate.getMinutes();
      const day = istDate.getDay();

      const isWeekday = day >= 1 && day <= 5;
      const totalMinutes = hours * 60 + minutes;
      const isOpen = isWeekday && totalMinutes >= 9 * 60 + 15 && totalMinutes <= 15 * 60 + 30;

      setMarketStatus(isOpen ? "LIVE TRADING SESSION" : "MARKET CLOSED (OFF-SESSION)");

      setTimeStr(
        istDate.toLocaleTimeString("en-IN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        }) + " IST"
      );
    }

    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  const [indices, setIndices] = useState<Record<string, any>>({});
  const [unreadAlerts, setUnreadAlerts] = useState<number>(0);

  // Dynamic Market Indices & Alert Summary Auto-Sync
  useEffect(() => {
    const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    async function loadIndicesAndAlerts() {
      try {
        const [mktRes, altRes] = await Promise.all([
          fetch(`${API}/api/market/indices`, { cache: "no-store" }).catch(() => null),
          fetch(`${API}/api/alerts/summary`, { cache: "no-store" }).catch(() => null),
        ]);

        if (mktRes && mktRes.ok) {
          const data = await mktRes.json();
          if (data?.indices) {
            setIndices(data.indices);
          }
          if (data?.session_status) {
            setMarketStatus(data.session_status);
          }
        }

        if (altRes && altRes.ok) {
          const d = await altRes.json();
          setUnreadAlerts(d?.summary?.active_alerts ?? 0);
        }
      } catch {
        // Fallback to local clock status
      }
    }
    loadIndicesAndAlerts();
    const interval = setInterval(loadIndicesAndAlerts, 20000);
    return () => clearInterval(interval);
  }, []);

  const nifty = indices["NIFTY 50"];
  const sensex = indices["SENSEX"];
  const vix = indices["INDIA VIX"];
  const bankNifty = indices["BANK NIFTY"];

  // Global hotkey Ctrl+K / Cmd+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <>
      <header className="sticky top-0 z-50 w-full border-b border-white/[0.08] bg-[#05070a]/90 backdrop-blur-xl">
        {/* Top Institutional Market Ribbon */}
        <div className="hidden border-b border-white/[0.05] bg-black/40 px-4 py-1 sm:block text-[11px] font-mono text-slate-400">
          <div className="mx-auto flex max-w-7xl items-center justify-between">
            <div className="flex items-center gap-5 overflow-x-auto py-0.5">
              <div className="flex items-center gap-1.5 font-bold text-slate-300">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <span>DAKOTA INTELLIGENCE TERMINAL</span>
              </div>

              <div className="flex items-center gap-4">
                <span className="text-slate-400">
                  NIFTY 50:{" "}
                  <span className={(nifty?.change_pct ?? 0) >= 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                    {nifty?.last_price != null ? nifty.last_price.toLocaleString("en-IN") : "25,014.10"}
                  </span>{" "}
                  <span className={`text-[10px] ${(nifty?.change_pct ?? 0) >= 0 ? "text-emerald-500/80" : "text-rose-500/80"}`}>
                    {nifty?.change_pct != null ? `${nifty.change_pct >= 0 ? "+" : ""}${nifty.change_pct}%` : "+0.22%"}
                  </span>
                </span>
                <span className="text-slate-400">
                  SENSEX:{" "}
                  <span className={(sensex?.change_pct ?? 0) >= 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                    {sensex?.last_price != null ? sensex.last_price.toLocaleString("en-IN") : "81,688.45"}
                  </span>{" "}
                  <span className={`text-[10px] ${(sensex?.change_pct ?? 0) >= 0 ? "text-emerald-500/80" : "text-rose-500/80"}`}>
                    {sensex?.change_pct != null ? `${sensex.change_pct >= 0 ? "+" : ""}${sensex.change_pct}%` : "+0.18%"}
                  </span>
                </span>
                <span className="text-slate-400">
                  INDIA VIX:{" "}
                  <span className="text-cyan-400 font-semibold">
                    {vix?.last_price != null ? vix.last_price.toFixed(2) : "13.12"}
                  </span>{" "}
                  <span className="text-cyan-500/80 text-[10px]">
                    {vix?.change_pct != null ? `${vix.change_pct >= 0 ? "+" : ""}${vix.change_pct}%` : "-2.45%"}
                  </span>
                </span>
                <span className="hidden lg:inline text-slate-400">
                  BANK NIFTY:{" "}
                  <span className={(bankNifty?.change_pct ?? 0) >= 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                    {bankNifty?.last_price != null ? bankNifty.last_price.toLocaleString("en-IN") : "51,280.00"}
                  </span>{" "}
                  <span className={`text-[10px] ${(bankNifty?.change_pct ?? 0) >= 0 ? "text-emerald-500/80" : "text-rose-500/80"}`}>
                    {bankNifty?.change_pct != null ? `${bankNifty.change_pct >= 0 ? "+" : ""}${bankNifty.change_pct}%` : "+0.35%"}
                  </span>
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3 shrink-0">
              <span className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-slate-300">
                {marketStatus}
              </span>
              <span className="text-slate-400 font-medium">
                {timeStr || "09:15:00 IST"}
              </span>
            </div>
          </div>
        </div>

        {/* Main Navigation Bar */}
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-2.5 sm:px-6">
          {/* Left: Brand Logo & Institutional Tag */}
          <div className="flex items-center gap-4">
            <Link href="/" className="flex items-center gap-2.5 group">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 shadow-sm shadow-cyan-500/20 group-hover:border-cyan-400 group-hover:bg-cyan-500/20 transition">
                <Activity className="h-4 w-4" />
              </div>
              <div className="leading-tight">
                <div className="flex items-center gap-1.5">
                  <span className="text-base font-black tracking-wider text-white group-hover:text-cyan-300 transition">
                    DAKOTA
                  </span>
                  <span className="rounded bg-cyan-500/10 px-1 py-0.2 text-[9px] font-mono font-bold text-cyan-400 border border-cyan-500/20">
                    FORENSIC
                  </span>
                </div>
                <div className="text-[10px] font-medium tracking-tight text-slate-500">
                  Financial Surveillance Engine
                </div>
              </div>
            </Link>

            {/* Desktop Navigation Links */}
            <nav className="hidden md:flex items-center gap-1 pl-4">
              {NAV_LINKS.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
                const badgeText = item.href === "/watcher" && unreadAlerts > 0 ? `${unreadAlerts}` : item.badge;

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`relative flex items-center gap-2 rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                      isActive
                        ? "bg-white/[0.08] text-white shadow-sm ring-1 ring-white/10"
                        : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200"
                    }`}
                  >
                    <Icon className={`h-3.5 w-3.5 ${isActive ? "text-cyan-400" : "text-slate-500"}`} />
                    <span>{item.label}</span>
                    {badgeText && (
                      <span className={`text-[9px] px-1.5 py-0.2 rounded font-mono font-bold ${
                        item.href === "/watcher" && unreadAlerts > 0
                          ? "bg-rose-500/25 text-rose-300 border border-rose-500/40 shadow-sm shadow-rose-500/30 animate-pulse"
                          : item.badge === "LIVE"
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : item.badge === "CARTEL"
                          ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                          : item.badge === "CORE"
                          ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 shadow-sm shadow-cyan-500/20"
                          : "bg-white/10 text-slate-400"
                      }`}>
                        {badgeText}
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Right: Global Command Search & Actions */}
          <div className="flex items-center gap-2.5">
            {/* Watcher Notification Bell */}
            <Link
              href="/watcher"
              className="relative flex items-center justify-center h-8 w-8 rounded-xl border border-white/[0.08] bg-white/[0.03] text-slate-400 hover:text-white hover:border-rose-500/40 transition"
              title="Surveillance Watcher & Alerts"
            >
              <Bell className="h-4 w-4" />
              {unreadAlerts > 0 && (
                <span className="absolute -top-1 -right-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-mono font-bold text-white shadow-sm shadow-rose-500/50 animate-pulse">
                  {unreadAlerts > 9 ? "9+" : unreadAlerts}
                </span>
              )}
            </Link>

            {/* Direct AI Copilot Link */}
            <Link
              href="/intelligence"
              className="hidden lg:flex items-center gap-1.5 rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20 transition shadow-sm shadow-cyan-500/20"
            >
              <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
              <span>Copilot</span>
            </Link>

            {/* Quick Command Palette Button */}
            <button
              onClick={() => setPaletteOpen(true)}
              className="flex items-center gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-slate-400 hover:border-cyan-500/40 hover:bg-white/[0.06] hover:text-white transition shadow-inner group"
            >
              <Search className="h-3.5 w-3.5 text-slate-400 group-hover:text-cyan-400 transition" />
              <span className="hidden sm:inline">Search equities, tips...</span>
              <span className="inline sm:hidden">Search</span>
              <kbd className="hidden sm:inline-flex items-center rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
                ⌘K
              </kbd>
            </button>

            {/* Mobile Hamburger Toggle */}
            <button
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              className="md:hidden flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-slate-400 hover:text-white"
            >
              {mobileMenuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {/* Mobile Dropdown Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="border-t border-white/10 bg-[#070b12] p-4 md:hidden animate-in slide-in-from-top-2">
            <div className="space-y-1">
              {NAV_LINKS.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileMenuOpen(false)}
                    className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
                      isActive
                        ? "bg-cyan-500/10 text-cyan-300 border border-cyan-500/20"
                        : "text-slate-400 hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <Icon className="h-4 w-4" />
                      <span>{item.label}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {item.badge && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 font-mono text-slate-300">
                          {item.badge}
                        </span>
                      )}
                      <ChevronRight className="h-4 w-4 opacity-50" />
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        )}
      </header>

      {/* Global Interactive Command Palette */}
      <CommandPalette isOpen={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  );
}

export default function Navbar() {
  return (
    <Suspense
      fallback={
        <div className="mb-8 w-full rounded-2xl border border-white/5 bg-[#070b12]/50 p-4 text-center">
          <div className="h-5 w-48 animate-pulse rounded bg-zinc-800 mx-auto" />
        </div>
      }
    >
      <NavbarInner />
    </Suspense>
  );
}

