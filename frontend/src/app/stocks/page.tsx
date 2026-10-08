"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Navbar from "@/components/Navbar";

type Stock = {
  ticker: string;
  name: string;
  exchange: string;
  segment: string;
  role: string;
  score: number | null;
  band: string;
  verdict: string;
  as_of: string | null;
};

type StocksResponse = {
  count: number;
  stocks: Stock[];
};

export default function StocksPage() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadStocks() {
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/stocks`,
          {
            cache: "no-store",
          }
        );

        const data: StocksResponse | { detail?: string } =
          await response.json();

        if (!response.ok) {
          throw new Error(
            "detail" in data && data.detail
              ? data.detail
              : "Could not load stocks."
          );
        }

        setStocks((data as StocksResponse).stocks);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Could not load stocks."
        );
      } finally {
        setLoading(false);
      }
    }

    loadStocks();
  }, []);

  function bandClass(band: string) {
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
            Portfolio Intelligence
          </p>

          <h1 className="mt-3 text-5xl font-bold">
            Stocks
          </h1>

          <p className="mt-4 max-w-3xl text-lg text-zinc-400">
            Explore Dakota risk indicators across the configured
            stock universe.
          </p>
        </header>

        {/* Loading */}
        {loading && (
          <div className="mt-10 rounded-2xl border border-zinc-800 bg-zinc-950 p-8">
            <p className="text-zinc-400">
              Calculating Dakota risk scores...
            </p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-10 rounded-2xl border border-red-900 bg-red-950/30 p-6">
            <p className="text-red-300">
              {error}
            </p>
          </div>
        )}

        {/* Stock table */}
        {!loading && !error && (
          <section className="mt-10 overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950">

            <div className="border-b border-zinc-800 px-6 py-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold">
                    Risk Screener
                  </h2>

                  <p className="mt-1 text-sm text-zinc-500">
                    {stocks.length} stocks in the current universe
                  </p>
                </div>
              </div>
            </div>

            {/* Desktop table */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-zinc-800 text-left text-xs uppercase tracking-wider text-zinc-500">
                    <th className="px-6 py-4">
                      Company
                    </th>

                    <th className="px-6 py-4">
                      Exchange
                    </th>

                    <th className="px-6 py-4">
                      Segment
                    </th>

                    <th className="px-6 py-4 text-right">
                      Risk
                    </th>

                    <th className="px-6 py-4">
                      Status
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {stocks.map((stock) => (
                    <tr
                      key={stock.ticker}
                      className="border-b border-zinc-900 transition hover:bg-zinc-900/50"
                    >
                      <td className="px-6 py-5">
                        <Link
                          href={`/stocks/${stock.ticker}`}
                          className="block"
                        >
                          <div className="font-semibold hover:text-zinc-300">
                            {stock.ticker}
                          </div>

                          <div className="mt-1 text-sm text-zinc-500">
                            {stock.name}
                          </div>
                        </Link>
                      </td>

                      <td className="px-6 py-5 text-sm text-zinc-400">
                        {stock.exchange}
                      </td>

                      <td className="px-6 py-5 text-sm text-zinc-400">
                        {stock.segment}
                      </td>

                      <td className="px-6 py-5 text-right">
                        <span className="text-lg font-semibold">
                          {stock.score ?? "—"}
                        </span>

                        {stock.score != null && (
                          <span className="text-zinc-600">
                            /100
                          </span>
                        )}
                      </td>

                      <td className="px-6 py-5">
                        <span
                          className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${bandClass(
                            stock.band
                          )}`}
                        >
                          {stock.band}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="divide-y divide-zinc-900 md:hidden">
              {stocks.map((stock) => (
                <Link
                  key={stock.ticker}
                  href={`/stocks/${stock.ticker}`}
                  className="block p-5 transition hover:bg-zinc-900/50"
                >
                  <div className="flex items-start justify-between gap-4">

                    <div>
                      <div className="font-semibold">
                        {stock.ticker}
                      </div>

                      <div className="mt-1 text-sm text-zinc-500">
                        {stock.name}
                      </div>

                      <div className="mt-3 text-xs text-zinc-600">
                        {stock.exchange} • {stock.segment}
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-xl font-bold">
                        {stock.score ?? "—"}
                      </div>

                      <span
                        className={`mt-2 inline-flex rounded-full border px-3 py-1 text-xs font-medium ${bandClass(
                          stock.band
                        )}`}
                      >
                        {stock.band}
                      </span>
                    </div>

                  </div>
                </Link>
              ))}
            </div>

          </section>
        )}

        <div className="mt-8">
          <Link
            href="/"
            className="inline-block rounded-xl bg-white px-5 py-3 font-semibold text-black transition hover:bg-zinc-200"
          >
            Back to Tip Check
          </Link>
        </div>

        <footer className="mt-16 border-t border-zinc-900 pt-6 text-sm text-zinc-600">
          Dakota • Evidence-based risk indicators
        </footer>

      </div>
    </main>
  );
}