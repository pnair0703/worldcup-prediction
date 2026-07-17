"use client";

import { useEffect, useState } from "react";
import CalibrationChart from "./components/CalibrationChart";
import ChatWidget from "./components/ChatWidget";
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

interface MarketMetrics {
  market: string;
  n: number;
  model: { accuracy: number; brier: number };
  base_rate: { accuracy: number; brier: number };
  naive: { accuracy: number | null; brier: number | null; label: string } | null;
}

interface CalibBucket {
  label: string;
  mid: number;
  n: number;
  mean_conf: number | null;
  win_rate: number | null;
}

export default function Home() {
  const [league, setLeague] = useState("EPL");
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [markets, setMarkets] = useState<MarketMetrics[]>([]);
  const [calibration, setCalibration] = useState<CalibBucket[]>([]);
  const [loadingFixtures, setLoadingFixtures] = useState(true);
  const [loadingMetrics, setLoadingMetrics] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoadingFixtures(true);
    setLoadingMetrics(true);
    setError(null);

    const apiLeague = league === "EPL_2026" ? "EPL" : league;
    const seasonParam = league === "EPL_2026" ? "&season=2026" : "";

    fetch(`/api/predictions?league=${apiLeague}${seasonParam}`)
      .then((r) => r.json())
      .then(setFixtures)
      .catch(() => setError("Failed to load predictions."))
      .finally(() => setLoadingFixtures(false));

    fetch(`/api/metrics?league=${apiLeague}`)
      .then((r) => r.json())
      .then((d) => { setMarkets(d.markets ?? []); setCalibration(d.calibration ?? []); })
      .catch(() => {})
      .finally(() => setLoadingMetrics(false));
  }, [league]);

  return (
    <main className="max-w-5xl mx-auto px-4 py-10">
      {/* header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white tracking-tight mb-1">
          Footy Oracle
        </h1>
        <p className="text-gray-400 text-sm">
          Mixture-of-Experts XGBoost · self-grading accuracy scoreboard · EPL + WC 2026
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

      {/* accuracy scoreboard + calibration */}
      <section>
        <h2 className="text-lg font-semibold text-white mb-1">
          Accuracy Scoreboard
        </h2>
        <p className="text-xs text-gray-500 mb-4">
          Model vs baselines — every finished fixture is scored against actual
          results. Brier score measures calibration (lower = better).
        </p>

        {loadingMetrics ? (
          <div className="h-32 animate-pulse bg-surface border border-border rounded-xl" />
        ) : (
          <div className="space-y-4">
            <div className="bg-surface border border-border rounded-xl p-5">
              <Scoreboard markets={markets} />
            </div>

            <div className="bg-surface border border-border rounded-xl p-5">
              <h3 className="text-sm font-semibold text-white mb-3">
                Calibration — Reliability Diagram
              </h3>
              <CalibrationChart buckets={calibration} />
            </div>
          </div>
        )}
      </section>

      <ChatWidget />
    </main>
  );
}
