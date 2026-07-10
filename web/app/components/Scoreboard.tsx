interface AccuracyEntry {
  market: string;
  total: number;
  correct: number;
  accuracy: number | null;
  avg_brier: number | null;
}

const MARKET_LABELS: Record<string, string> = {
  RESULT: "Result",
  OVER_UNDER_2_5: "O/U 2.5 Goals",
  BTTS: "Both Teams Score",
  SCORELINE: "Scoreline",
};

function pct(v: number | null): string {
  return v == null ? "—" : `${(v * 100).toFixed(1)}%`;
}

function brier(v: number | null): string {
  return v == null ? "—" : v.toFixed(3);
}

export default function Scoreboard({ data }: { data: AccuracyEntry[] }) {
  if (data.length === 0) {
    return (
      <p className="text-gray-500 text-sm">
        No graded predictions yet. Come back after some matches have been played.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-border">
            <th className="text-left py-2 pr-4">Market</th>
            <th className="text-right py-2 px-4">Graded</th>
            <th className="text-right py-2 px-4">Correct</th>
            <th className="text-right py-2 px-4">Accuracy</th>
            <th className="text-right py-2 pl-4">Avg Brier</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.market} className="border-b border-border last:border-0">
              <td className="py-3 pr-4 text-white font-medium">
                {MARKET_LABELS[row.market] ?? row.market}
              </td>
              <td className="text-right py-3 px-4 text-gray-300">{row.total}</td>
              <td className="text-right py-3 px-4 text-gray-300">{row.correct}</td>
              <td className="text-right py-3 px-4">
                <span
                  className={
                    row.accuracy != null && row.accuracy >= 0.5
                      ? "text-green-400 font-semibold"
                      : "text-gray-300"
                  }
                >
                  {pct(row.accuracy)}
                </span>
              </td>
              <td className="text-right py-3 pl-4 text-gray-300 font-mono text-xs">
                {brier(row.avg_brier)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
