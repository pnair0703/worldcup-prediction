"use client";

interface Props {
  league: string;
  onChange: (l: string) => void;
}

const LEAGUES = [
  { key: "EPL", label: "Premier League" },
  { key: "WORLD_CUP", label: "World Cup 2026" },
];

export default function LeagueToggle({ league, onChange }: Props) {
  return (
    <div className="flex gap-2">
      {LEAGUES.map((l) => (
        <button
          key={l.key}
          onClick={() => onChange(l.key)}
          className={`px-4 py-2 rounded-full text-sm font-semibold transition-colors ${
            league === l.key
              ? l.key === "EPL"
                ? "bg-epl text-white"
                : "bg-wc text-pitch"
              : "bg-surface text-gray-400 hover:text-white border border-border"
          }`}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
