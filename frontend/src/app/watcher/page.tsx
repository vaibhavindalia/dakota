"use client";

import { useEffect, useMemo, useState } from "react";
import Navbar from "@/components/Navbar";

type Risk = {
  score?: number;
  band?: string;
  verdict?: string;
  as_of?: string;
  reasons?: string[];
  next_steps?: string[];
  contributions?: Record<string, number>;
  contribution_labels?: Record<string, string>;
};

type Holding = {
  ticker: string;
  name: string;
  exchange: string;
  quantity: number;
  average_buy_price: number | null;
  risk?: Risk | null;
};

type Portfolio = {
  name: string;
  holdings: Holding[];
};

type WatchEvent = {
  ticker: string;
  name: string;
  score: number | null;
  band: string;
  reason: string;
};

export default function WatcherPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadWatcher() {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/portfolio`,
        {
          cache: "no-store",
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail || "Could not load Watcher data."
        );
      }

      setPortfolio(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not load Watcher data."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadWatcher();
  }, []);

  const events = useMemo<WatchEvent[]>(() => {
    if (!portfolio) {
      return [];
    }

    const output: WatchEvent[] = [];

    for (const holding of portfolio.holdings) {
      const risk = holding.risk;

      if (!risk) {
        continue;
      }

      const reasons = risk.reasons ?? [];

      for (const reason of reasons.slice(0, 4)) {
        output.push({
          ticker: holding.ticker,
          name: holding.name,
          score:
            typeof risk.score === "number"
              ? risk.score
              : null,
          band: risk.band ?? "Unknown",
          reason,
        });
      }
    }

    return output;
  }, [portfolio]);

  function riskClass(band?: string) {
    if (band === "High") {
      return "border-red-900/60 bg-red-950/30 text-red-300";
    }

    if (band === "Elevated") {
      return "border-orange-900/60 bg-orange-950/30 text-orange-300";
    }

    if (band === "Low") {
      return "border-emerald-900/60 bg-emerald-950/30 text-emerald-300";
    }

    return "border-zinc-800 bg-zinc-900 text-zinc-400";
  }

  const highRiskCount =
    portfolio?.holdings.filter(
      (holding) => holding.risk?.band === "High"
    ).length ?? 0;

  const elevatedCount =
    portfolio?.holdings.filter(
      (holding) => holding.risk?.band === "Elevated"
    ).length ?? 0;

  return (
    <main className="min-h-screen bg-black text-white">
      <div className="mx-auto max-w-6xl px-6 py-16">

        <Navbar />

        <header>
          <p className="text-sm uppercase tracking-[0.3em] text-zinc-500">
            Portfolio Watcher
          </p>

          <h1 className="mt-3 text-5xl font-bold">
            What Changed?
          </h1>

          <p className="mt-4 max-w-3xl text-lg text-zinc-400">
            Dakota watches the stocks in your portfolio and surfaces
            the signals that deserve attention.
          </p>
        </header>

        {error && (
          <div className="mt-8 rounded-2xl border border-red-900 bg-red-950/30 p-5 text-red-300">
            {error}
          </div>
        )}

        {loading ? (
          <div className="mt-10 rounded-2xl border border-zinc-800 bg-zinc-950 p-8 text-zinc-500">
            Loading your Watcher...
          </div>
        ) : (
          <>
            {/* Summary */}
            <section className="mt-10 grid gap-4 md:grid-cols-4">

              <SummaryCard
                label="Watched Stocks"
                value={String(
                  portfolio?.holdings.length ?? 0
                )}
              />

              <SummaryCard
                label="High Risk"
                value={String(highRiskCount)}
              />

              <SummaryCard
                label="Elevated"
                value={String(elevatedCount)}
              />

              <SummaryCard
                label="Signals"
                value={String(events.length)}
              />

            </section>

            {/* Holdings */}
            <section className="mt-8">
              <div className="mb-5">
                <h2 className="text-2xl font-semibold">
                  Portfolio Watch
                </h2>

                <p className="mt-1 text-sm text-zinc-500">
                  Current Dakota signals for every holding.
                </p>
              </div>

              {portfolio?.holdings.length === 0 ? (
                <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-8">
                  <p className="text-zinc-300">
                    Your portfolio is empty.
                  </p>

                  <p className="mt-2 text-sm text-zinc-600">
                    Add holdings from the Portfolio page to start
                    the Watcher.
                  </p>
                </div>
              ) : (
                <div className="grid gap-5 lg:grid-cols-2">
                  {portfolio?.holdings.map((holding) => {
                    const risk = holding.risk;

                    return (
                      <article
                        key={holding.ticker}
                        className="rounded-2xl border border-zinc-800 bg-zinc-950 p-6"
                      >
                        <div className="flex items-start justify-between gap-4">

                          <div>
                            <p className="text-2xl font-bold">
                              {holding.ticker}
                            </p>

                            <p className="mt-1 text-sm text-zinc-500">
                              {holding.name}
                            </p>

                            <p className="mt-2 text-xs text-zinc-600">
                              {holding.exchange} •{" "}
                              {holding.quantity} shares
                            </p>
                          </div>

                          <div className="text-right">
                            <div className="text-4xl font-bold">
                              {risk?.score ?? "—"}
                              {risk?.score != null && (
                                <span className="text-lg text-zinc-600">
                                  /100
                                </span>
                              )}
                            </div>

                            <span
                              className={`mt-2 inline-flex rounded-full border px-3 py-1 text-xs font-medium ${riskClass(
                                risk?.band
                              )}`}
                            >
                              {risk?.band ?? "No data"}
                            </span>
                          </div>

                        </div>

                        <div className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
                          <p className="text-xs uppercase tracking-wider text-zinc-600">
                            Current assessment
                          </p>

                          <p className="mt-2 text-sm text-zinc-300">
                            {risk?.verdict ??
                              "No risk assessment available."}
                          </p>
                        </div>

                        <div className="mt-6">
                          <p className="text-sm font-semibold">
                            Signals
                          </p>

                          {risk?.reasons &&
                          risk.reasons.length > 0 ? (
                            <div className="mt-3 space-y-2">
                              {risk.reasons
                                .slice(0, 5)
                                .map((reason, index) => (
                                  <div
                                    key={`${reason}-${index}`}
                                    className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-3 text-sm text-zinc-400"
                                  >
                                    • {reason}
                                  </div>
                                ))}
                            </div>
                          ) : (
                            <p className="mt-3 text-sm text-zinc-600">
                              No current signals.
                            </p>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </section>

            {/* Activity feed */}
            <section className="mt-12">
              <h2 className="text-2xl font-semibold">
                Intelligence Feed
              </h2>

              <p className="mt-1 text-sm text-zinc-500">
                This is the foundation for the future live
                market + news + Telegram watcher.
              </p>

              <div className="mt-5 rounded-2xl border border-zinc-800 bg-zinc-950">
                {events.length === 0 ? (
                  <div className="p-8 text-sm text-zinc-600">
                    No signals are currently available.
                  </div>
                ) : (
                  <div className="divide-y divide-zinc-900">
                    {events.map((event, index) => (
                      <div
                        key={`${event.ticker}-${index}`}
                        className="flex flex-col gap-3 p-5 md:flex-row md:items-center md:justify-between"
                      >
                        <div>
                          <div className="flex items-center gap-3">
                            <span className="font-semibold">
                              {event.ticker}
                            </span>

                            <span
                              className={`rounded-full border px-2.5 py-1 text-xs ${riskClass(
                                event.band
                              )}`}
                            >
                              {event.band}
                            </span>
                          </div>

                          <p className="mt-2 text-sm text-zinc-400">
                            {event.reason}
                          </p>
                        </div>

                        <div className="text-sm text-zinc-600">
                          Risk {event.score ?? "—"}/100
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          </>
        )}

        <footer className="mt-16 border-t border-zinc-900 pt-6 text-sm text-zinc-600">
          Dakota • Portfolio Watcher
        </footer>

      </div>
    </main>
  );
}


function SummaryCard({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-5">
      <p className="text-xs uppercase tracking-wider text-zinc-600">
        {label}
      </p>

      <p className="mt-2 text-3xl font-bold">
        {value}
      </p>
    </div>
  );
}