
export default function MarketBadges({ observations }: { observations: any[] }) {
  if (!observations || observations.length === 0) return null;
  return (
    <div className="mt-8 rounded-2xl border border-zinc-800 bg-zinc-950 p-6">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 mb-4">Market Footprint (Mathematical Analysis)</h3>
      <div className="flex flex-wrap gap-3">
        {observations.map((obs, i) => {
          const isHigh = obs.severity === 'high' || (obs.text && obs.text.toLowerCase().includes('volume')) || (obs.text && obs.text.toLowerCase().includes('rsi'));
          const isLow = obs.severity === 'low' || (obs.text && obs.text.toLowerCase().includes('trend'));
          const colorClass = isHigh ? 'border-red-500/50 bg-red-950 text-red-400' : (isLow ? 'border-green-500/50 bg-green-950 text-green-400' : 'border-yellow-500/50 bg-yellow-950 text-yellow-400');
          return (
            <div key={i} className={`flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium ${colorClass}`}>
              <span className="h-2 w-2 rounded-full bg-current"></span>
              {obs.text || obs.signal}
            </div>
          );
        })}
      </div>
    </div>
  );
}
