"""Database access for the pipeline (Python side).

Reads DATABASE_URL from the environment (a Neon Postgres connection string).
Keep all SQL in one place so the rest of the pipeline stays clean.
"""

import json
import os

import psycopg2
import psycopg2.extras


def get_conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and add your "
            "Neon connection string."
        )
    return psycopg2.connect(url)


def init_schema(conn, schema_path: str = "db/schema.sql") -> None:
    with open(schema_path) as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def upsert_fixture(conn, fx: dict) -> int:
    """Insert/update a fixture, return its primary key id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO fixtures
                (league, source_match_id, season, kickoff_utc, home_team,
                 away_team, stage, home_goals, away_goals, status)
            VALUES
                (%(league)s, %(source_match_id)s, %(season)s, %(kickoff_utc)s,
                 %(home_team)s, %(away_team)s, %(stage)s, %(home_goals)s,
                 %(away_goals)s, %(status)s)
            ON CONFLICT (league, source_match_id) DO UPDATE SET
                kickoff_utc = EXCLUDED.kickoff_utc,
                home_goals  = EXCLUDED.home_goals,
                away_goals  = EXCLUDED.away_goals,
                status      = EXCLUDED.status
            RETURNING id;
            """,
            fx,
        )
        fixture_id = cur.fetchone()[0]
    conn.commit()
    return fixture_id


def upsert_prediction(conn, pred: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO predictions
                (fixture_id, market, probs, predicted, confidence, model_version, expert_used)
            VALUES
                (%(fixture_id)s, %(market)s, %(probs)s, %(predicted)s,
                 %(confidence)s, %(model_version)s, %(expert_used)s)
            ON CONFLICT (fixture_id, market, model_version) DO UPDATE SET
                probs       = EXCLUDED.probs,
                predicted   = EXCLUDED.predicted,
                confidence  = EXCLUDED.confidence,
                expert_used = EXCLUDED.expert_used,
                created_at  = now()
            RETURNING id;
            """,
            {**pred, "probs": json.dumps(pred["probs"]), "expert_used": pred.get("expert_used")},
        )
        pred_id = cur.fetchone()[0]
    conn.commit()
    return pred_id


def upsert_grade(conn, grade: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO grades
                (prediction_id, fixture_id, league, market, actual, correct, brier)
            VALUES
                (%(prediction_id)s, %(fixture_id)s, %(league)s, %(market)s,
                 %(actual)s, %(correct)s, %(brier)s)
            ON CONFLICT (prediction_id) DO NOTHING;
            """,
            grade,
        )
    conn.commit()


def fetch_finished_ungraded(conn, league: str) -> list[dict]:
    """Predictions whose fixture is finished but which have no grade yet."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT p.id AS prediction_id, p.fixture_id, p.market, p.probs,
                   p.predicted, f.league, f.home_goals, f.away_goals
            FROM predictions p
            JOIN fixtures f ON f.id = p.fixture_id
            LEFT JOIN grades g ON g.prediction_id = p.id
            WHERE f.status = 'FINISHED'
              AND f.league = %s
              AND g.id IS NULL;
            """,
            (league,),
        )
        return [dict(r) for r in cur.fetchall()]
