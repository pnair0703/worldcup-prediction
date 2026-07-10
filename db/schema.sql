-- footy-oracle schema (Neon Postgres)
-- The Python pipeline writes here; the Next.js serverless layer reads here.

-- One row per match we know about (past or upcoming), per competition.
CREATE TABLE IF NOT EXISTS fixtures (
    id              BIGSERIAL PRIMARY KEY,
    league          TEXT        NOT NULL,          -- 'EPL' | 'WORLD_CUP'
    source_match_id TEXT        NOT NULL,          -- id from the upstream data source
    season          TEXT        NOT NULL,
    kickoff_utc     TIMESTAMPTZ NOT NULL,
    home_team       TEXT        NOT NULL,
    away_team       TEXT        NOT NULL,
    stage           TEXT,                          -- 'GROUP' | 'R32' | 'LEAGUE' etc.
    -- actual result, filled in once the match is played
    home_goals      INT,
    away_goals      INT,
    status          TEXT        NOT NULL DEFAULT 'SCHEDULED', -- SCHEDULED | FINISHED
    UNIQUE (league, source_match_id)
);

CREATE INDEX IF NOT EXISTS idx_fixtures_league_kickoff ON fixtures (league, kickoff_utc);
CREATE INDEX IF NOT EXISTS idx_fixtures_status ON fixtures (status);

-- One row per (fixture, market) prediction. A fixture has several markets.
CREATE TABLE IF NOT EXISTS predictions (
    id            BIGSERIAL PRIMARY KEY,
    fixture_id    BIGINT      NOT NULL REFERENCES fixtures (id) ON DELETE CASCADE,
    market        TEXT        NOT NULL,    -- 'RESULT' | 'OVER_UNDER_2_5' | 'BTTS' | 'SCORELINE'
    -- probabilities stored as JSON so each market can have its own label set
    -- RESULT: {"home":0.55,"draw":0.25,"away":0.20}
    -- OVER_UNDER_2_5: {"over":0.6,"under":0.4}
    -- BTTS: {"yes":0.48,"no":0.52}
    -- SCORELINE: {"2-1":0.11,"1-0":0.10,...}
    probs         JSONB       NOT NULL,
    predicted     TEXT        NOT NULL,    -- argmax label, for quick display/grading
    confidence    REAL        NOT NULL,    -- max prob, for the UI confidence bar
    model_version TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (fixture_id, market, model_version)
);

CREATE INDEX IF NOT EXISTS idx_predictions_fixture ON predictions (fixture_id);

-- One row per graded prediction, written by the eval step once a match finishes.
-- This table powers the live accuracy scoreboard.
CREATE TABLE IF NOT EXISTS grades (
    id            BIGSERIAL PRIMARY KEY,
    prediction_id BIGINT      NOT NULL REFERENCES predictions (id) ON DELETE CASCADE,
    fixture_id    BIGINT      NOT NULL REFERENCES fixtures (id) ON DELETE CASCADE,
    league        TEXT        NOT NULL,
    market        TEXT        NOT NULL,
    actual        TEXT        NOT NULL,    -- the realized label
    correct       BOOLEAN     NOT NULL,    -- predicted == actual
    brier         REAL        NOT NULL,    -- multiclass Brier score for calibration
    graded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (prediction_id)
);

CREATE INDEX IF NOT EXISTS idx_grades_league_market ON grades (league, market);
