"use client";

import { useState } from "react";
import Navbar from "@/components/Navbar";

type ParsedTip = {
  clean_text?: string;
  tickers?: string[];
  price_target?: number | null;
  markers_found?: Record<string, string[]>;
  n_scam_markers?: number;
  urgency?: boolean;
  sebi_reg_claimed?: boolean;
  sebi_reg_number?: string | null;
  sebi_reg_verified?: boolean | null;
  fingerprint?: string;
};

type StockVerdict = {
  ticker: string;
  as_of?: string;
  score: number;
  band: string;
  verdict: string;
  contributions?: Record<string, number>;
  contribution_labels?: Record<string, string>;
  reasons?: string[];
  next_steps?: string[];
};

type TipResult = {
  parsed?: ParsedTip;
  stock_verdicts?: StockVerdict[];
  headline?: string;
  tip_level_reasons?: string[];
  combined_reasons?: string[];
  next_steps?: string[];
  disclaimer?: string;
};

export default function Home() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<TipResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function analyzeTip() {
    if (!text.trim()) {
      setError("Please paste a stock tip first.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/tip/check`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            text: text.trim(),
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail || "Dakota could not analyze this tip."
        );
      }

      setResult(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong."
      );
    } finally {
      setLoading(false);
    }
  }

  const stock = result?.stock_verdicts?.[0];
  const parsed = result?.parsed;

  return (
    <main className="min-h-screen bg-black text-white">
      <div className="mx-auto max-w-5xl px-6 py-16">

        <Navbar />

        <header className="mb-12">
          <p className="mb-3 text-sm uppercase tracking-[0.3em] text-zinc-500">
            Portfolio Intelligence
          </p>

          <h1 className="text-6xl font-bold tracking-tight">
            Dakota
          </h1>

          <p className="mt-5 max-w-2xl text-xl text-zinc-400">
            Forward the tip. Check the stock. See the evidence.
          </p>

          <p className="mt-3 text-sm text-zinc-600">
            Risk indicators — not accusations, not investment advice.
          </p>
        </header>

        <section className="rounded-2xl border border-zinc-800 bg-zinc-950 p-6">
          <h2 className="text-2xl font-semibold">
            Check Before You Buy
          </h2>

          <p className="mt-2 text-sm text-zinc-500">
            Paste a forwarded WhatsApp, Telegram or SMS stock tip.
          </p>

          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={
              "Example:\nURGENT BUY VARANIUM TARGET ₹500.\nGuaranteed returns. VIP group entry today."
            }
            className="mt-6 min-h-48 w-full resize-y rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-base text-white outline-none placeholder:text-zinc-600 focus:border-zinc-500"
          />

          <button
            onClick={analyzeTip}
            disabled={loading}
            className="mt-4 rounded-xl bg-white px-6 py-3 font-semibold text-black transition hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Analyzing..." : "Analyze Tip"}
          </button>

          {error && (
            <div className="mt-5 rounded-xl border border-red-900 bg-red-950/30 p-4 text-sm text-red-300">
              {error}
            </div>
          )}
        </section>

        {stock && (
          <section className="mt-8 rounded-2xl border border-zinc-800 bg-zinc-950 p-6">

            <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="text-sm uppercase tracking-widest text-zinc-500">
                  Detected Stock
                </p>

                <h2 className="mt-2 text-3xl font-bold">
                  {stock.ticker}
                </h2>

                {stock.as_of && (
                  <p className="mt-2 text-sm text-zinc-500">
                    As of {stock.as_of}
                  </p>
                )}
              </div>

              <div className="md:text-right">
                <div className="text-5xl font-bold">
                  {stock.score}
                  <span className="text-2xl text-zinc-500">
                    /100
                  </span>
                </div>

                <div className="mt-1 text-lg text-orange-400">
                  {stock.band}
                </div>
              </div>
            </div>

            <div className="mt-8 rounded-xl border border-orange-900/50 bg-orange-950/20 p-5">
              <p className="text-sm font-semibold uppercase tracking-wider text-orange-400">
                Assessment
              </p>

              <p className="mt-2 text-zinc-200">
                {stock.verdict}
              </p>
            </div>

            {parsed && (
              <div className="mt-8">
                <h3 className="text-lg font-semibold">
                  Tip Signals
                </h3>

                <div className="mt-4 grid gap-4 sm:grid-cols-3">
                  <SignalCard
                    label="Ticker"
                    value={
                      parsed.tickers && parsed.tickers.length > 0
                        ? parsed.tickers.join(", ")
                        : "Not detected"
                    }
                  />

                  <SignalCard
                    label="Price Target"
                    value={
                      parsed.price_target != null
                        ? `₹${parsed.price_target.toLocaleString("en-IN")}`
                        : "Not detected"
                    }
                  />

                  <SignalCard
                    label="Scam Markers"
                    value={String(parsed.n_scam_markers ?? 0)}
                  />
                </div>

                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <SignalCard
                    label="Urgency"
                    value={
                      parsed.urgency
                        ? "Detected"
                        : "Not detected"
                    }
                  />

                  <SignalCard
                    label="SEBI Registration"
                    value={
                      parsed.sebi_reg_claimed
                        ? parsed.sebi_reg_number
                          ? `Claimed: ${parsed.sebi_reg_number}`
                          : "Claimed, number not shown"
                        : "Not claimed"
                    }
                  />
                </div>
              </div>
            )}

            {result.combined_reasons &&
              result.combined_reasons.length > 0 && (
                <div className="mt-8">
                  <h3 className="text-lg font-semibold">
                    Evidence
                  </h3>

                  <div className="mt-4 space-y-3">
                    {result.combined_reasons.map(
                      (reason, index) => (
                        <div
                          key={`${reason}-${index}`}
                          className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-300"
                        >
                          • {reason}
                        </div>
                      )
                    )}
                  </div>
                </div>
              )}

            {stock.contributions && (
              <div className="mt-8">
                <h3 className="text-lg font-semibold">
                  Risk Breakdown
                </h3>

                <div className="mt-5 space-y-5">
                  {Object.entries(stock.contributions).map(
                    ([key, value]) => (
                      <div key={key}>
                        <div className="mb-2 flex justify-between text-sm">
                          <span className="text-zinc-400">
                            {stock.contribution_labels?.[key] ??
                              key}
                          </span>

                          <span className="font-semibold">
                            {value}
                          </span>
                        </div>

                        <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
                          <div
                            className="h-full rounded-full bg-white"
                            style={{
                              width: `${Math.min(
                                Number(value) * 4,
                                100
                              )}%`,
                            }}
                          />
                        </div>
                      </div>
                    )
                  )}
                </div>
              </div>
            )}

            {result.next_steps &&
              result.next_steps.length > 0 && (
                <div className="mt-8 rounded-xl border border-zinc-800 bg-zinc-900 p-5">
                  <h3 className="text-lg font-semibold">
                    Next Steps
                  </h3>

                  <div className="mt-4 space-y-2 text-sm text-zinc-300">
                    {result.next_steps.map(
                      (step, index) => (
                        <p key={`${step}-${index}`}>
                          {index + 1}. {step}
                        </p>
                      )
                    )}
                  </div>
                </div>
              )}

            {result.disclaimer && (
              <p className="mt-8 text-xs leading-5 text-zinc-600">
                {result.disclaimer}
              </p>
            )}
          </section>
        )}

        <footer className="mt-16 border-t border-zinc-900 pt-6 text-sm text-zinc-600">
          Dakota • Evidence-based risk indicators
        </footer>
      </div>
    </main>
  );
}

function SignalCard({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <p className="text-xs uppercase tracking-wider text-zinc-500">
        {label}
      </p>

      <p className="mt-2 text-lg font-semibold">
        {value}
      </p>
    </div>
  );
}