"use client";

import { FormEvent, useEffect, useState } from "react";
import Navbar from "@/components/Navbar";

type Risk = {
  score?: number;
  band?: string;
  verdict?: string;
  as_of?: string;
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

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");
  const [averagePrice, setAveragePrice] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function loadPortfolio() {
    try {
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
          data?.detail || "Could not load portfolio."
        );
      }

      setPortfolio(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not load portfolio."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPortfolio();
  }, []);

  async function addHolding(event: FormEvent) {
    event.preventDefault();

    if (!ticker.trim()) {
      setError("Enter a stock ticker.");
      return;
    }

    if (!quantity || Number(quantity) <= 0) {
      setError("Enter a valid quantity.");
      return;
    }

    setSaving(true);
    setError("");

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/portfolio/holdings`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            ticker: ticker.trim().toUpperCase(),
            quantity: Number(quantity),
            average_buy_price: averagePrice
              ? Number(averagePrice)
              : null,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail || "Could not add holding."
        );
      }

      setTicker("");
      setQuantity("");
      setAveragePrice("");

      await loadPortfolio();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not add holding."
      );
    } finally {
      setSaving(false);
    }
  }

  async function removeHolding(stockTicker: string) {
    try {
      setError("");

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/portfolio/holdings/${encodeURIComponent(
          stockTicker
        )}`,
        {
          method: "DELETE",
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail || "Could not remove holding."
        );
      }

      await loadPortfolio();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not remove holding."
      );
    }
  }

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

  return (
    <main className="min-h-screen bg-black text-white">
      <div className="mx-auto max-w-6xl px-6 py-16">

        <Navbar />

        <header>
          <p className="text-sm uppercase tracking-[0.3em] text-zinc-500">
            Watcher
          </p>

          <h1 className="mt-3 text-5xl font-bold">
            My Portfolio
          </h1>

          <p className="mt-4 max-w-3xl text-lg text-zinc-400">
            Tell Dakota which stocks to watch. The Watcher will
            eventually combine market activity, news and tips around
            these holdings.
          </p>
        </header>

        {error && (
          <div className="mt-8 rounded-2xl border border-red-900 bg-red-950/30 p-5 text-red-300">
            {error}
          </div>
        )}

        {/* Add holding */}
        <section className="mt-10 rounded-2xl border border-zinc-800 bg-zinc-950 p-6">
          <h2 className="text-xl font-semibold">
            Add Holding
          </h2>

          <p className="mt-2 text-sm text-zinc-500">
            For now, holdings must exist in Dakota&apos;s configured universe.
          </p>

          <form
            onSubmit={addHolding}
            className="mt-6 grid gap-4 md:grid-cols-4"
          >
            <input
              value={ticker}
              onChange={(event) =>
                setTicker(event.target.value)
              }
              placeholder="Ticker e.g. CLOUD"
              className="rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3 text-white outline-none placeholder:text-zinc-600 focus:border-zinc-500"
            />

            <input
              value={quantity}
              onChange={(event) =>
                setQuantity(event.target.value)
              }
              type="number"
              min="0"
              step="any"
              placeholder="Quantity"
              className="rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3 text-white outline-none placeholder:text-zinc-600 focus:border-zinc-500"
            />

            <input
              value={averagePrice}
              onChange={(event) =>
                setAveragePrice(event.target.value)
              }
              type="number"
              min="0"
              step="any"
              placeholder="Average buy price (optional)"
              className="rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3 text-white outline-none placeholder:text-zinc-600 focus:border-zinc-500"
            />

            <button
              type="submit"
              disabled={saving}
              className="rounded-xl bg-white px-5 py-3 font-semibold text-black transition hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? "Adding..." : "Add Holding"}
            </button>
          </form>
        </section>

        {/* Holdings */}
        <section className="mt-8 rounded-2xl border border-zinc-800 bg-zinc-950">

          <div className="border-b border-zinc-800 px-6 py-5">
            <h2 className="text-xl font-semibold">
              Holdings
            </h2>

            <p className="mt-1 text-sm text-zinc-500">
              {portfolio?.holdings.length ?? 0} stocks being watched
            </p>
          </div>

          {loading ? (
            <div className="p-8 text-zinc-500">
              Loading portfolio...
            </div>
          ) : portfolio?.holdings.length === 0 ? (
            <div className="p-8">
              <p className="text-zinc-300">
                No holdings yet.
              </p>

              <p className="mt-2 text-sm text-zinc-600">
                Add your first stock above to start building
                the Watcher.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-zinc-900">
              {portfolio?.holdings.map((holding) => (
                <div
                  key={holding.ticker}
                  className="flex flex-col gap-5 p-6 md:flex-row md:items-center md:justify-between"
                >
                  <div>
                    <div className="flex items-center gap-3">
                      <h3 className="text-xl font-semibold">
                        {holding.ticker}
                      </h3>

                      {holding.risk?.band && (
                        <span
                          className={`rounded-full border px-3 py-1 text-xs font-medium ${riskClass(
                            holding.risk.band
                          )}`}
                        >
                          {holding.risk.band}
                        </span>
                      )}
                    </div>

                    <p className="mt-1 text-sm text-zinc-500">
                      {holding.name}
                    </p>

                    <p className="mt-3 text-sm text-zinc-600">
                      {holding.exchange} •{" "}
                      {holding.quantity} shares
                      {holding.average_buy_price != null
                        ? ` • Avg ₹${holding.average_buy_price}`
                        : ""}
                    </p>
                  </div>

                  <div className="flex items-center gap-6">
                    <div className="text-right">
                      <div className="text-3xl font-bold">
                        {holding.risk?.score ?? "—"}
                      </div>

                      <div className="text-xs text-zinc-600">
                        Dakota risk / 100
                      </div>
                    </div>

                    <button
                      onClick={() =>
                        removeHolding(holding.ticker)
                      }
                      className="rounded-xl border border-zinc-800 px-4 py-2 text-sm text-zinc-400 transition hover:border-red-900 hover:text-red-300"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <footer className="mt-16 border-t border-zinc-900 pt-6 text-sm text-zinc-600">
          Dakota • Portfolio Watcher
        </footer>

      </div>
    </main>
  );
}