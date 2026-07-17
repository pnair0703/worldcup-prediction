import { NextRequest, NextResponse } from "next/server";
import sql from "@/lib/db";

export const dynamic = "force-dynamic";

interface GradeRow {
  market: string;
  actual: string;
  correct: boolean;
  brier: number;
  confidence: number;
}

function brierForPred(probs: Record<string, number>, actual: string): number {
  return Object.entries(probs).reduce((s, [cls, p]) => s + (p - (cls === actual ? 1 : 0)) ** 2, 0);
}

// Naive fixed-prediction baselines (always predict the "favourite" label)
const ALWAYS_PRED: Record<string, Record<string, number>> = {
  RESULT:       { home: 1, draw: 0, away: 0 },
  OVER_UNDER_2_5: { over: 1, under: 0 },
  BTTS:         { yes: 1, no: 0 },
};

export async function GET(req: NextRequest) {
  const league = req.nextUrl.searchParams.get("league") ?? "EPL";

  const rows = (await sql`
    SELECT
      g.market,
      g.actual,
      g.correct,
      g.brier,
      p.confidence
    FROM grades g
    JOIN predictions p ON p.id = g.prediction_id
    WHERE g.league = ${league}
    ORDER BY g.market
  `) as GradeRow[];

  // ── per-market stats ────────────────────────────────────────────────────────
  const byMarket = new Map<string, GradeRow[]>();
  for (const row of rows) {
    if (!byMarket.has(row.market)) byMarket.set(row.market, []);
    byMarket.get(row.market)!.push(row);
  }

  const markets = [];
  for (const [market, mrows] of byMarket.entries()) {
    if (market === "SCORELINE") continue;

    const n = mrows.length;
    if (n === 0) continue;

    const modelBrier  = mrows.reduce((s, r) => s + Number(r.brier), 0) / n;
    const modelAcc    = mrows.filter((r) => r.correct).length / n;

    // Base-rate: compute outcome distribution from actuals, use as probs for every prediction
    const counts: Record<string, number> = {};
    for (const r of mrows) counts[r.actual] = (counts[r.actual] ?? 0) + 1;
    const rates: Record<string, number> = {};
    for (const [cls, c] of Object.entries(counts)) rates[cls] = c / n;

    const baseRateMode = Object.entries(rates).sort((a, b) => b[1] - a[1])[0][0];
    const baseRateAcc  = (counts[baseRateMode] ?? 0) / n;
    const baseRateBrier = mrows.reduce((s, r) => s + brierForPred(rates, r.actual), 0) / n;

    // Always-home / always-over / always-yes
    const naivePred = ALWAYS_PRED[market];
    let naiveAcc = null, naiveBrier = null;
    if (naivePred) {
      const naiveLabel = Object.entries(naivePred).find(([, v]) => v === 1)![0];
      naiveAcc   = (counts[naiveLabel] ?? 0) / n;
      naiveBrier = mrows.reduce((s, r) => s + brierForPred(naivePred, r.actual), 0) / n;
    }

    markets.push({ market, n, model: { accuracy: modelAcc, brier: modelBrier },
      base_rate: { accuracy: baseRateAcc, brier: baseRateBrier },
      naive: naivePred ? { accuracy: naiveAcc, brier: naiveBrier, label: Object.entries(naivePred).find(([, v]) => v === 1)![0] } : null,
    });
  }

  // ── calibration buckets (non-scoreline predictions) ─────────────────────────
  const calibRows = rows.filter((r) => r.market !== "SCORELINE");
  const EDGES = [0.5, 0.6, 0.7, 0.8, 0.9, 1.01];
  const calibration = EDGES.slice(0, -1).map((lo, i) => {
    const hi = EDGES[i + 1];
    const bucket = calibRows.filter((r) => {
      const c = Number(r.confidence);
      return c >= lo && c < hi;
    });
    return {
      label: `${Math.round(lo * 100)}–${Math.round(Math.min(hi, 1) * 100)}%`,
      mid: (lo + Math.min(hi, 1)) / 2,
      n: bucket.length,
      mean_conf: bucket.length > 0 ? bucket.reduce((s, r) => s + Number(r.confidence), 0) / bucket.length : null,
      win_rate:  bucket.length > 0 ? bucket.filter((r) => r.correct).length / bucket.length : null,
    };
  });

  return NextResponse.json({ markets, calibration });
}
