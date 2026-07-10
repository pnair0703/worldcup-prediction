import { NextRequest, NextResponse } from "next/server";
import sql from "@/lib/db";

export const dynamic = "force-dynamic";

interface AccuracyRow {
  market: string;
  total: number;
  correct_count: number;
  avg_brier: number;
}

export async function GET(req: NextRequest) {
  const league = req.nextUrl.searchParams.get("league") ?? "EPL";

  const rows = (await sql`
    SELECT
      market,
      COUNT(*)                                        AS total,
      SUM(CASE WHEN correct THEN 1 ELSE 0 END)       AS correct_count,
      AVG(brier)                                      AS avg_brier
    FROM grades
    WHERE league = ${league}
    GROUP BY market
    ORDER BY market
  `) as AccuracyRow[];

  const result = rows.map((r) => ({
    market: r.market,
    total: Number(r.total),
    correct: Number(r.correct_count),
    accuracy: r.total > 0 ? Number(r.correct_count) / Number(r.total) : null,
    avg_brier: r.avg_brier != null ? Number(r.avg_brier) : null,
  }));

  return NextResponse.json(result);
}
