import { NextRequest, NextResponse } from "next/server";
import sql from "@/lib/db";

export const dynamic = "force-dynamic";

interface PredictionRow {
  fixture_id: number;
  kickoff_utc: string;
  home_team: string;
  away_team: string;
  stage: string;
  market: string;
  probs: Record<string, number>;
  predicted: string;
  confidence: number;
  model_version: string;
}

export async function GET(req: NextRequest) {
  const league = req.nextUrl.searchParams.get("league") ?? "EPL";

  const rows = await sql<PredictionRow[]>`
    SELECT
      f.id           AS fixture_id,
      f.kickoff_utc,
      f.home_team,
      f.away_team,
      f.stage,
      p.market,
      p.probs,
      p.predicted,
      p.confidence,
      p.model_version
    FROM fixtures f
    JOIN predictions p ON p.fixture_id = f.id
    WHERE f.league        = ${league}
      AND f.status        = 'SCHEDULED'
      AND f.kickoff_utc   > NOW() - INTERVAL '2 hours'
    ORDER BY f.kickoff_utc ASC, p.market
    LIMIT 200
  `;

  // group by fixture
  const byFixture = new Map<
    number,
    {
      id: number;
      kickoff_utc: string;
      home_team: string;
      away_team: string;
      stage: string;
      predictions: Record<
        string,
        { probs: Record<string, number>; predicted: string; confidence: number }
      >;
    }
  >();

  for (const row of rows) {
    if (!byFixture.has(row.fixture_id)) {
      byFixture.set(row.fixture_id, {
        id: row.fixture_id,
        kickoff_utc: row.kickoff_utc,
        home_team: row.home_team,
        away_team: row.away_team,
        stage: row.stage,
        predictions: {},
      });
    }
    byFixture.get(row.fixture_id)!.predictions[row.market] = {
      probs: row.probs,
      predicted: row.predicted,
      confidence: row.confidence,
    };
  }

  return NextResponse.json(Array.from(byFixture.values()));
}
