import ConfidenceBar from "./ConfidenceBar";

interface Prediction {
  probs: Record<string, number>;
  predicted: string;
  confidence: number;
}

interface Fixture {
  id: number;
  kickoff_utc: string;
  home_team: string;
  away_team: string;
  stage: string;
  predictions: Record<string, Prediction>;
}

const MARKET_LABELS: Record<string, string> = {
  RESULT: "Result",
  OVER_UNDER_2_5: "O/U 2.5",
  BTTS: "BTTS",
  SCORELINE: "Scoreline",
};

const MARKET_ORDER = ["RESULT", "OVER_UNDER_2_5", "BTTS", "SCORELINE"];

function fmtKickoff(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  });
}

export default function FixtureCard({ fixture }: { fixture: Fixture }) {
  const markets = MARKET_ORDER.filter((m) => m in fixture.predictions);

  return (
    <div className="bg-surface border border-border rounded-xl p-5 flex flex-col gap-4">
      {/* header */}
      <div>
        <p className="text-xs text-gray-500 mb-1">
          {fixture.stage} · {fmtKickoff(fixture.kickoff_utc)}
        </p>
        <div className="flex items-center justify-between">
          <span className="font-semibold text-white">{fixture.home_team}</span>
          <span className="text-gray-500 text-sm mx-3">vs</span>
          <span className="font-semibold text-white text-right">
            {fixture.away_team}
          </span>
        </div>
      </div>

      {/* markets */}
      <div className="flex flex-col gap-3">
        {markets.map((m) => {
          const pred = fixture.predictions[m];
          const teamNames = { home: fixture.home_team, away: fixture.away_team };
          const predictedLabel =
            m === "RESULT"
              ? pred.predicted === "home"
                ? fixture.home_team
                : pred.predicted === "away"
                ? fixture.away_team
                : "Draw"
              : pred.predicted;
          return (
            <div key={m}>
              <div className="flex justify-between items-center mb-1">
                <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                  {MARKET_LABELS[m] ?? m}
                </span>
                {m !== "SCORELINE" && (
                  <span className="text-xs text-gray-300">
                    {predictedLabel} &middot;{" "}
                    <span className="font-semibold text-white">
                      {(pred.confidence * 100).toFixed(0)}%
                    </span>
                  </span>
                )}
              </div>
              <ConfidenceBar
                probs={pred.probs}
                market={m}
                teamNames={m === "RESULT" ? teamNames : undefined}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
