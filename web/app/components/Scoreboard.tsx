interface MarketMetrics {
  market: string;
  n: number;
  model: { accuracy: number; brier: number };
  base_rate: { accuracy: number; brier: number };
  naive: { accuracy: number | null; brier: number | null; label: string } | null;
}

const MARKET_LABELS: Record<string, string> = {
  RESULT: "Result",
  OVER_UNDER_2_5: "O/U 2.5 Goals",
  BTTS: "Both Teams Score",
};

const NAIVE_LABELS: Record<string, string> = {
  RESULT: "Always home",
  OVER_UNDER_2_5: "Always over",
  BTTS: "Always yes",
};

function pct(v: number | null): string {
  return v == null ? "—" : `${(v * 100).toFixed(1)}%`;
}

function br(v: number | null): string {
  return v == null ? "—" : v.toFixed(3);
}

function Delta({ model, baseline }: { model: number; baseline: number }) {
  const diff = model - baseline;
  // For Brier lower is better, for accuracy higher is better
  // This component is generic — caller decides sign interpretation
  const pos = diff > 0;
  return (
    <span className={pos ? "text-green-400" : "text-red-400"}>
      {pos ? "+" : "−"}{Math.abs(diff * 100).toFixed(1)}pp
    </span>
  );
}

interface Props {
  markets: MarketMetrics[];
}

export default function Scoreboard({ markets }: Props) {
  if (markets.length === 0) {
    return (
      <p className="text-gray-500 text-sm">
        No graded predictions yet. Come back after some matches have been played.
      </p>
    );
  }

  const totalN = markets.reduce((s, m) => s + m.n, 0);

  return (
    <div className="space-y-5">
      {totalN < 50 && (
        <p className="text-xs text-amber-400 bg-amber-400/10 border border-amber-400/20 rounded-lg px-3 py-2">
          Only {totalN} graded predictions — sample too small for conclusions. Numbers will stabilise after ~50 matches per market.
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-border">
              <th className="text-left py-2 pr-4">Market</th>
              <th className="text-right py-2 px-3">n</th>
              <th className="text-right py-2 px-3 text-white">Model acc.</th>
              <th className="text-right py-2 px-3">Base-rate</th>
              <th className="text-right py-2 px-3">{""}</th>
              <th className="text-right py-2 px-3 text-white">Model Brier ↓</th>
              <th className="text-right py-2 px-3">Base-rate</th>
              <th className="text-right py-2 pl-3">{""}</th>
            </tr>
          </thead>
          <tbody>
            {markets.map((row) => {
              const accDiff = row.model.accuracy - row.base_rate.accuracy;
              // Brier: lower is better, so negative diff is good
              const brierDiff = row.model.brier - row.base_rate.brier;
              return (
                <tr key={row.market} className="border-b border-border last:border-0">
                  <td className="py-3 pr-4 text-white font-medium">
                    {MARKET_LABELS[row.market] ?? row.market}
                  </td>
                  <td className="text-right py-3 px-3 text-gray-500 text-xs">{row.n}</td>

                  {/* Accuracy */}
                  <td className="text-right py-3 px-3 font-semibold text-white">
                    {pct(row.model.accuracy)}
                  </td>
                  <td className="text-right py-3 px-3 text-gray-400">
                    {pct(row.base_rate.accuracy)}
                    {row.naive && (
                      <span className="block text-gray-600 text-xs">
                        {NAIVE_LABELS[row.market]}: {pct(row.naive.accuracy)}
                      </span>
                    )}
                  </td>
                  <td className="text-right py-3 px-3 text-xs">
                    <span className={accDiff >= 0 ? "text-green-400" : "text-red-400"}>
                      {accDiff >= 0 ? "+" : "−"}{Math.abs(accDiff * 100).toFixed(1)}pp
                    </span>
                  </td>

                  {/* Brier */}
                  <td className="text-right py-3 px-3 font-semibold text-white font-mono text-xs">
                    {br(row.model.brier)}
                  </td>
                  <td className="text-right py-3 px-3 text-gray-400 font-mono text-xs">
                    {br(row.base_rate.brier)}
                    {row.naive && (
                      <span className="block text-gray-600">
                        {br(row.naive.brier)}
                      </span>
                    )}
                  </td>
                  <td className="text-right py-3 pl-3 text-xs">
                    {/* Brier: lower is better, so negative brierDiff = model is better */}
                    <span className={brierDiff <= 0 ? "text-green-400" : "text-red-400"}>
                      {brierDiff <= 0 ? "−" : "+"}{Math.abs(brierDiff).toFixed(3)}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-600">
        Base-rate = predict historical outcome frequency every match. Always-home/over/yes = dumbest possible fixed predictor. Green = model beats baseline.
      </p>
    </div>
  );
}
