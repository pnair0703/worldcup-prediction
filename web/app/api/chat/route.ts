import { streamText, tool } from "ai";
import { createGroq } from "@ai-sdk/groq";
import { z } from "zod";
import sql from "@/lib/db";

export const dynamic = "force-dynamic";
export const runtime = "edge";

const groq = createGroq({ apiKey: process.env.GROQ_API_KEY ?? "" });

const SYSTEM = `You are Footy Oracle's AI assistant — a football prediction expert powered by an
XGBoost + Bivariate Poisson Mixture-of-Experts model trained on EPL and World Cup 2026 data.

You have tools to query live prediction data from the database. Always call a tool to get
actual data before answering questions about specific matches or accuracy figures.

MoE routing context for your explanations:
- EPL: "full" expert uses all 3 seasons of data (stronger when |elo_diff| > 150).
       "recent" expert uses last 2 seasons (stronger for closely-matched teams).
- WC:  "group" expert trained on group-stage matches (higher scoring, more draws).
       "knockout" expert trained on knockout matches (tight, low-scoring).

Be concise, cite confidence percentages, and mention the expert used when explaining predictions.`;

export async function POST(req: Request) {
  const { messages } = await req.json();

  const result = streamText({
    model: groq("llama-3.3-70b-versatile"),
    system: SYSTEM,
    messages,
    maxSteps: 5,
    tools: {
      getUpcomingPredictions: tool({
        description: "Get upcoming fixture predictions for a league (EPL or WORLD_CUP)",
        parameters: z.object({
          league: z.enum(["EPL", "WORLD_CUP"]).describe("The league to query"),
        }),
        execute: async ({ league }) => {
          const rows = (await sql`
            SELECT
              f.home_team, f.away_team, f.kickoff_utc, f.stage,
              p.market, p.predicted, p.confidence, p.probs, p.expert_used
            FROM fixtures f
            JOIN predictions p ON p.fixture_id = f.id
            WHERE f.league = ${league}
              AND f.status = 'SCHEDULED'
              AND f.kickoff_utc > NOW() - INTERVAL '2 hours'
            ORDER BY f.kickoff_utc ASC, p.market
            LIMIT 60
          `) as Array<Record<string, unknown>>;
          return rows;
        },
      }),

      getTeamForm: tool({
        description: "Get a team's last 5 results (goals for/against, points)",
        parameters: z.object({
          team: z.string().describe("Team name to look up"),
          league: z.enum(["EPL", "WORLD_CUP"]).describe("The league"),
        }),
        execute: async ({ team, league }) => {
          const rows = (await sql`
            SELECT
              kickoff_utc,
              CASE WHEN home_team = ${team} THEN away_team ELSE home_team END AS opponent,
              CASE WHEN home_team = ${team} THEN 'home' ELSE 'away' END AS venue,
              home_goals, away_goals,
              CASE
                WHEN home_team = ${team} AND home_goals > away_goals THEN 'W'
                WHEN away_team = ${team} AND away_goals > home_goals THEN 'W'
                WHEN home_goals = away_goals THEN 'D'
                ELSE 'L'
              END AS result
            FROM fixtures
            WHERE league = ${league}
              AND (home_team = ${team} OR away_team = ${team})
              AND status = 'FINISHED'
              AND home_goals IS NOT NULL
            ORDER BY kickoff_utc DESC
            LIMIT 5
          `) as Array<Record<string, unknown>>;
          return rows;
        },
      }),

      getModelAccuracy: tool({
        description: "Get model accuracy and Brier score by market for a league",
        parameters: z.object({
          league: z.enum(["EPL", "WORLD_CUP"]),
        }),
        execute: async ({ league }) => {
          const rows = (await sql`
            SELECT
              market,
              COUNT(*)                                  AS total,
              SUM(CASE WHEN correct THEN 1 ELSE 0 END) AS correct_count,
              AVG(brier)                                AS avg_brier
            FROM grades
            WHERE league = ${league}
            GROUP BY market
            ORDER BY market
          `) as Array<Record<string, unknown>>;
          return rows.map((r) => ({
            market: r.market,
            total: Number(r.total),
            correct: Number(r.correct_count),
            accuracy: Number(r.total) > 0
              ? Math.round((Number(r.correct_count) / Number(r.total)) * 1000) / 10
              : null,
            avg_brier: r.avg_brier != null ? Math.round(Number(r.avg_brier) * 10000) / 10000 : null,
          }));
        },
      }),

      explainPrediction: tool({
        description: "Explain a specific fixture prediction including which MoE expert was used",
        parameters: z.object({
          home_team: z.string(),
          away_team: z.string(),
          league: z.enum(["EPL", "WORLD_CUP"]),
        }),
        execute: async ({ home_team, away_team, league }) => {
          const rows = (await sql`
            SELECT
              f.home_team, f.away_team, f.kickoff_utc, f.stage,
              p.market, p.probs, p.predicted, p.confidence, p.expert_used
            FROM fixtures f
            JOIN predictions p ON p.fixture_id = f.id
            WHERE f.league = ${league}
              AND f.status = 'SCHEDULED'
              AND LOWER(f.home_team) LIKE ${"%" + home_team.toLowerCase() + "%"}
              AND LOWER(f.away_team) LIKE ${"%" + away_team.toLowerCase() + "%"}
            ORDER BY f.kickoff_utc ASC, p.market
            LIMIT 10
          `) as Array<Record<string, unknown>>;
          return rows;
        },
      }),
    },
  });

  return result.toDataStreamResponse();
}
