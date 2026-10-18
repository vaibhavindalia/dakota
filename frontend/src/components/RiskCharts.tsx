"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

type Stock = {
  ticker: string;
  name: string;
  score: number | null;
  band: string;
};

export function TopRiskChart({ stocks }: { stocks: Stock[] }) {
  // Get top 5 riskiest stocks > 0
  const data = stocks
    .filter((s) => (s.score ?? 0) > 0)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, 5)
    .map((s) => ({
      name: s.ticker,
      score: s.score,
      band: s.band,
    }));

  if (data.length === 0) return (
    <div className="h-64 w-full mt-4 flex items-center justify-center text-zinc-500 border border-zinc-800 rounded-xl bg-zinc-900/50">
      No risky stocks detected yet.
    </div>
  );

  return (
    <div className="h-64 w-full mt-4 p-4 border border-zinc-800 rounded-xl bg-zinc-950">
      <h3 className="text-sm uppercase tracking-wider text-zinc-400 mb-4 font-semibold">Top Risk Distribution</h3>
      <ResponsiveContainer width="100%" height="80%">
        <BarChart data={data} layout="vertical" margin={{ left: 40, right: 20 }}>
          <XAxis type="number" domain={[0, 100]} hide />
          <YAxis
            dataKey="name"
            type="category"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#a1a1aa", fontSize: 12 }}
          />
          <Tooltip
            cursor={{ fill: "#27272a" }}
            contentStyle={{ backgroundColor: "#09090b", borderColor: "#27272a", borderRadius: "8px" }}
            itemStyle={{ color: "#ef4444" }}
          />
          <Bar dataKey="score" radius={[0, 4, 4, 0]}>
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={
                  entry.band === "High"
                    ? "#b91c1c" // red-700
                    : entry.band === "Elevated"
                    ? "#c2410c" // orange-700
                    : "#047857" // emerald-700
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
