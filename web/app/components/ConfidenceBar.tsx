interface Segment {
  label: string;
  prob: number;
  color: string;
}

interface Props {
  probs: Record<string, number>;
  market: string;
  teamNames?: { home: string; away: string };
}

const MARKET_COLORS: Record<string, Record<string, string>> = {
  RESULT: { home: "#3d0aff", draw: "#6b7280", away: "#ef4444" },
  OVER_UNDER_2_5: { over: "#10b981", under: "#6b7280" },
  BTTS: { yes: "#f59e0b", no: "#6b7280" },
  SCORELINE: {},
};

const MARKET_ORDER: Record<string, string[]> = {
  RESULT: ["home", "draw", "away"],
  OVER_UNDER_2_5: ["over", "under"],
  BTTS: ["yes", "no"],
};

function resolveLabel(key: string, teamNames?: { home: string; away: string }): string {
  if (!teamNames) return key;
  if (key === "home") return teamNames.home;
  if (key === "away") return teamNames.away;
  return key;
}

export default function ConfidenceBar({ probs, market, teamNames }: Props) {
  if (market === "SCORELINE") {
    const top = Object.entries(probs)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5);
    return (
      <div className="flex flex-wrap gap-2 mt-1">
        {top.map(([score, p]) => (
          <span
            key={score}
            className="text-xs bg-surface border border-border rounded px-2 py-0.5 font-mono"
          >
            {score}{" "}
            <span className="text-gray-400">{(p * 100).toFixed(1)}%</span>
          </span>
        ))}
      </div>
    );
  }

  const order = MARKET_ORDER[market] ?? Object.keys(probs);
  const colors = MARKET_COLORS[market] ?? {};
  const segments: Segment[] = order
    .filter((k) => k in probs)
    .map((k) => ({ label: resolveLabel(k, teamNames), prob: probs[k], color: colors[k] ?? "#6b7280" }));

  return (
    <div>
      <div className="flex h-2 rounded-full overflow-hidden w-full">
        {segments.map((s) => (
          <div
            key={s.label}
            style={{ width: `${s.prob * 100}%`, background: s.color }}
          />
        ))}
      </div>
      <div className="flex justify-between mt-1">
        {segments.map((s) => (
          <span key={s.label} className="text-xs text-gray-400">
            <span style={{ color: s.color }}>{s.label}</span>{" "}
            {(s.prob * 100).toFixed(0)}%
          </span>
        ))}
      </div>
    </div>
  );
}
