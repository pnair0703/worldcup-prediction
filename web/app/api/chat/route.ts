import { streamText, tool } from "ai";
import { createGroq } from "@ai-sdk/groq";
import { z } from "zod";
import sql from "@/lib/db";

export const dynamic = "force-dynamic";
export const runtime = "edge";

const groq = createGroq({ apiKey: process.env.GROQ_API_KEY ?? "" });

const SYSTEM = `You are Footy Oracle AI — a football prediction assistant backed by a live database.

CURRENT CONTEXT: The FIFA World Cup 2026 Final is on July 19 (Spain vs Argentina).
The 3rd-place match is July 18 (France vs England). This is the highest-priority topic.

You have four tools that return REAL data. You MUST call a tool before answering any football question.

Tool selection rules:
• getUpcomingPredictions — for ANY match/prediction question. Default league = WORLD_CUP unless the user clearly asks about EPL/Premier League.
  - Mentions of Spain, Argentina, France, England, Brazil, Germany, or any national team → WORLD_CUP
  - "Final", "World Cup", "WC" → WORLD_CUP
  - "Premier League", "EPL", club names (Arsenal, Man City, etc.) → EPL
  - Generic ("who wins tomorrow", "any games?") → WORLD_CUP first
• getTeamForm      — specific team's recent form (specify league)
• getModelAccuracy — model accuracy, Brier score questions
• explainPrediction — deep-dive one fixture by home + away team name

After the tool returns data, write 2–4 sentences. Lead with the prediction and confidence %, then one line of reasoning.
If the tool returns an empty list, try the other league before saying nothing is available.
Do NOT say you lack real-time data. You have live tools — use them.`;

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
              p.market, p.predicted, p.confidence, p.expert_used
            FROM fixtures f
            JOIN predictions p ON p.fixture_id = f.id
            WHERE f.league = ${league}
              AND f.status = 'SCHEDULED'
              AND f.kickoff_utc > NOW() - INTERVAL '2 hours'
              AND p.market != 'SCORELINE'
            ORDER BY f.kickoff_utc ASC, p.market
            LIMIT 30
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
              p.market, p.predicted, p.confidence, p.expert_used
            FROM fixtures f
            JOIN predictions p ON p.fixture_id = f.id
            WHERE f.league = ${league}
              AND f.status = 'SCHEDULED'
              AND p.market != 'SCORELINE'
              AND LOWER(f.home_team) LIKE ${"%" + home_team.toLowerCase() + "%"}
              AND LOWER(f.away_team) LIKE ${"%" + away_team.toLowerCase() + "%"}
            ORDER BY f.kickoff_utc ASC, p.market
            LIMIT 8
          `) as Array<Record<string, unknown>>;
          return rows;
        },
      }),
    },
  });

  return result.toDataStreamResponse();
}
