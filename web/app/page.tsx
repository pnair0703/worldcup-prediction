"use client";

import { useEffect, useState } from "react";
import FixtureCard from "./components/FixtureCard";
import LeagueToggle from "./components/LeagueToggle";
import Scoreboard from "./components/Scoreboard";

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

interface AccuracyEntry {
  market: string;
  total: number;
  correct: number;
  accuracy: number | null;
  avg_brier: number | null;
}

export default function Home() {
  const [league, setLeague] = useState("EPL");
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [accuracy, setAccuracy] = useState<AccuracyEntry[]>([]);
  const [loadingFixtures, setLoadingFixtures] = useState(true);
  const [loadingAccuracy, setLoadingAccuracy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoadingFixtures(true);
    setLoadingAccuracy(true);
    setError(null);

    fetch(`/api/predictions?league=${league}`)
      .then((r) => r.json())
      .then(setFixtures)
      .catch(() => setError("Failed to load predictions."))
      .finally(() => setLoadingFixtures(false));

    fetch(`/api/accuracy?league=${league}`)
      .then((r) => r.json())
      .then(setAccuracy)
      .catch(() => {})
      .finally(() => setLoadingAccuracy(false));
  }, [league]);

  return (
    <main className="max-w-5xl mx-auto px-4 py-10">
      {/* header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white tracking-tight mb-1">
          Footy Oracle
        </h1>
        <p className="text-gray-400 text-sm">
          XGBoost predictions · self-grading accuracy scoreboard · EPL + WC 2026
        </p>
      </div>

      {/* league toggle */}
      <div className="mb-6">
        <LeagueToggle league={league} onChange={setLeague} />
      </div>

      {/* upcoming fixtures */}
      <section className="mb-12">
        <h2 className="text-lg font-semibold text-white mb-4">
          Upcoming Fixtures
        </h2>

        {error && (
          <p className="text-red-400 text-sm">{error}</p>
        )}

        {loadingFixtures ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[...Array(4)].map((_, i) => (
              <div
                key={i}
                className="bg-surface border border-border rounded-xl h-48 animate-pulse"
              />
            ))}
          </div>
        ) : fixtures.length === 0 ? (
          <p className="text-gray-500 text-sm">
            No upcoming fixtures with predictions right now.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {fixtures.map((f) => (
              <FixtureCard key={f.id} fixture={f} />
            ))}
          </div>
        )}
      </section>

      {/* accuracy scoreboard */}
      <section>
        <h2 className="text-lg font-semibold text-white mb-1">
          Accuracy Scoreboard
        </h2>
        <p className="text-xs text-gray-500 mb-4">
          Live self-grading: every finished fixture is scored against actual
          results. Brier score measures calibration (lower = better).
        </p>

        {loadingAccuracy ? (
          <div className="h-32 animate-pulse bg-surface border border-border rounded-xl" />
        ) : (
          <div className="bg-surface border border-border rounded-xl p-5">
            <Scoreboard data={accuracy} />
          </div>
        )}
      </section>
    </main>
  );
}
