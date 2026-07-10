# footy-oracle — Architecture & Build Handoff

A self-running soccer match-prediction system. It ingests data daily, predicts
upcoming fixtures across several betting-style markets, serves those predictions
through a serverless web app, and **grades its own predictions against real
results over time** — the headline feature.

It runs **two competitions through one engine**:
- **EPL** — the durable flagship. Rich shot-level xG data, runs year-round.
- **World Cup 2026** — a live "skin" on the same engine while the tournament is
  on (ends July 19, 2026). Thin international data, so it leans on Elo + form.

This doc is the source of truth. Build to it. Where it says STUBBED or TODO,
that's work to do.

---

## 1. Design intent (don't lose this)

This is a portfolio project whose job is to prove the author can **build and
operate a real ML system in production**, targeting $150–200K MLE roles. The
things that matter, in priority order:

1. **It runs itself.** A scheduled job ingests → predicts → grades with zero
   manual touch. This is the single most important signal.
2. **It grades itself honestly.** A live accuracy scoreboard tracks accuracy and
   calibration (Brier score) per market over time. Real, self-updating metrics
   beat a one-time backtest number. Shows understanding of probabilistic
   calibration — exactly what ML interviewers probe.
3. **Real modeling depth, not an LLM wrapper.** Trained gradient-boosted models
   on engineered features (xG, Elo, form). This is deliberately NOT a GenAI
   project — the author already has several of those.
4. **Clean train/serve decoupling.** Python does offline modeling; Node serves.
   They communicate through Postgres. "I separated the offline pipeline from the
   online serving layer" is a strong interview line — preserve this split.

Anti-goals: don't turn this into an LLM/agent project; don't call any upstream
API's pre-baked predictions (e.g. some free football APIs ship their own
CatBoost predictions — never use those, we BUILD the model); don't merge Python
into the request path.

---

## 2. Architecture

```
┌─ Python (offline brain) ─ runs on GitHub Actions cron ─────────┐
│  scripts/daily_runner.py orchestrates:                         │
│   1. ingest  EPL (Understat xG + football-data.org fixtures)   │
│              World Cup (football-data.org only)                │
│   2. features (Elo + rolling form, + xG when available)        │
│   3. predict every upcoming fixture × every market             │
│   4. grade  yesterday's now-finished fixtures vs reality       │
│        │ writes via psycopg2                                   │
│        ▼                                                       │
│   ┌──────────────┐                                             │
└───│ Neon Postgres │─────────────────────────────────────────────┘
    └──────────────┘
        │ reads via @neondatabase/serverless
┌─ Node (online serving + UI) ─ Next.js on Vercel ──────────────┐
│   app/api/predictions  → upcoming fixtures + market probs     │
│   app/api/accuracy      → scoreboard aggregates               │
│   app/ (React)          → fixtures, confidence bars,          │
│                            EPL/World Cup toggle, scoreboard    │
└────────────────────────────────────────────────────────────────┘
```

**Why this stack:** serverless Node front (impressive, zero infra), Python ML
stays where the ecosystem lives, Postgres is the clean contract between them and
makes the time-series accuracy queries trivial.

---

## 3. Tech stack

| Layer        | Choice                          | Notes |
|--------------|---------------------------------|-------|
| Data (xG)    | Understat (`understat` pylib)   | EPL only, free, no key |
| Data (fixtures/results) | football-data.org API v4 | EPL (`PL`) + World Cup (`WC`); free key required |
| Features/models | Python, pandas, scikit-learn, **XGBoost** | gradient-boosted, multiclass |
| Store        | **Neon Postgres**               | serverless PG; Python writes, Node reads |
| Serving + UI | **Next.js (App Router) on Vercel** | serverless API routes + React |
| DB driver (Node) | `@neondatabase/serverless`  | HTTP driver, no pooling pain in serverless |
| Scheduler    | **GitHub Actions cron**         | runs `daily_runner.py` daily |

---

## 4. Repository layout

```
footy-oracle/
├── ARCHITECTURE.md            # this file
├── README.md                  # TODO: user-facing, with arch diagram + live accuracy table
├── .env.example               # TODO: list required env vars
├── db/
│   └── schema.sql             # DONE: fixtures, predictions, grades
├── pipeline/
│   ├── league.py              # DONE: League abstraction (EPL has xG, WC doesn't)
│   ├── db.py                  # DONE: psycopg2 helpers (upserts, fetch ungraded)
│   ├── ingest/
│   │   ├── football_data.py   # DONE: EPL + WC fixtures/results
│   │   └── understat.py       # DONE: EPL shot-level xG
│   ├── features/
│   │   └── build.py           # DONE: Elo + rolling form/xG, leak-safe
│   ├── models/
│   │   ├── result.py          # TODO: match-result model (home/draw/away)
│   │   ├── over_under.py      # STUB: O/U 2.5 goals
│   │   ├── btts.py            # STUB: both teams to score
│   │   └── scoreline.py       # STUB: Poisson scoreline
│   └── eval/
│       └── grade.py           # TODO: grade finished predictions, write Brier
├── scripts/
│   ├── daily_runner.py        # TODO: orchestrates ingest→features→predict→grade
│   └── backfill.py            # TODO: one-off historical load + initial train
├── web/                       # TODO: Next.js app
│   ├── app/
│   │   ├── page.tsx           # fixtures + predictions UI
│   │   ├── api/predictions/route.ts
│   │   ├── api/accuracy/route.ts
│   │   └── components/        # FixtureCard, ConfidenceBar, Scoreboard, LeagueToggle
│   └── lib/db.ts              # Neon client
├── .github/workflows/
│   ├── daily.yml              # TODO: cron → daily_runner
│   └── ci.yml                 # TODO: lint + test on push
└── requirements.txt           # TODO
```

### What already exists (read these first, build on them)
- `db/schema.sql` — the three tables. Predictions store `probs` as JSONB so each
  market carries its own label set. `grades` powers the scoreboard.
- `pipeline/league.py` — the `League` dataclass. Models train on exactly
  `League.feature_columns`. Adding a competition = new ingester + new League.
- `pipeline/db.py` — `get_conn`, `init_schema`, `upsert_fixture`,
  `upsert_prediction`, `upsert_grade`, `fetch_finished_ungraded`.
- `pipeline/ingest/football_data.py` — `fetch_fixtures(league, date_from, date_to)`
  returns normalized fixture dicts. Reads `FOOTBALL_DATA_API_KEY`.
- `pipeline/ingest/understat.py` — `fetch_epl_xg(season)` returns per-team,
  per-match xG rows for building rolling features.
- `pipeline/features/build.py` — `build_features(matches_df, league, xg_lookup)`.
  Elo with home-adv + margin-of-victory; rolling form. **Leak-safe**: state only
  updates on finished matches, so upcoming fixtures see only past info. Preserve
  this property in anything you add.

---

## 5. Data model (the Python↔Node contract)

- **fixtures** — one row per match per league. `status` ∈ SCHEDULED|FINISHED;
  goals null until played. Unique on `(league, source_match_id)`.
- **predictions** — one row per `(fixture, market, model_version)`. `probs` JSONB,
  plus argmax `predicted` and `confidence` for fast UI. Markets:
  `RESULT`, `OVER_UNDER_2_5`, `BTTS`, `SCORELINE`.
- **grades** — one row per graded prediction: `correct` + multiclass `brier`.
  Written only after the fixture finishes.

Node never computes predictions — it only reads these tables.

---

## 6. Build sequence (suggested order)

1. **Get it connectable.** `requirements.txt` (psycopg2-binary, pandas,
   scikit-learn, xgboost, requests, understat, aiohttp, python-dotenv).
   `.env.example` with `DATABASE_URL`, `FOOTBALL_DATA_API_KEY`. Run
   `init_schema` against Neon.
2. **`models/result.py` first** — the flagship market. XGBoost multiclass over
   `league.feature_columns`. A `train(df)` and a `predict_proba(df)` returning
   `{"home":..,"draw":..,"away":..}`. Persist the trained model (joblib) keyed by
   league + `model_version`.
3. **`scripts/backfill.py`** — load history (Understat seasons for EPL; WC group
   stage already played for World Cup), build features, train, write predictions
   for upcoming fixtures. This is what makes the first deploy show real output.
4. **`eval/grade.py`** — `fetch_finished_ungraded` → compute correct + Brier →
   `upsert_grade`. Brier = Σ(p_i − y_i)² over the market's classes.
5. **`scripts/daily_runner.py`** — ingest both leagues (today ± a window) →
   features → predict upcoming → grade finished. Idempotent (upserts).
6. **Next.js app** — `lib/db.ts` Neon client; `/api/predictions?league=EPL`
   and `/api/accuracy?league=EPL`; UI with fixture cards, confidence bars, the
   EPL/World Cup toggle, and the accuracy scoreboard.
7. **Automation** — `daily.yml` cron (set ~6am UTC), inject secrets, run
   `daily_runner`. `ci.yml` for lint/test.
8. **Then extend markets** — over_under, btts, scoreline reuse the same features
   and the same write path. Each is largely a new label + a model head.

---

## 7. Modeling notes

- **Markets share one feature matrix.** Build features once per fixture; each
  market is a different label/head over the same vector. Keep that factoring.
- **Scoreline** is cleanest as a Poisson model: predict home/away expected goals,
  derive a scoreline distribution, and you get O/U and BTTS *for free* by summing
  the right cells. Consider making `scoreline.py` the base and deriving O/U + BTTS
  from it rather than training them separately — stronger and more coherent. (Up
  to you; the schema supports either.)
- **EPL vs WC honesty.** WC has no xG and little history — lean on Elo + recent
  international form, report calibration honestly, don't fake xG. The scoreboard
  will (correctly) show WC predictions as less sharp; that's a feature, not a bug.
- **Leakage.** `build.py` only updates Elo/form on FINISHED matches. Any new
  feature must respect this — never let an upcoming fixture see its own result or
  future matches.

---

## 8. Environment variables

| Var | Used by | How to get |
|-----|---------|-----------|
| `DATABASE_URL` | Python + Node | Neon project connection string (free tier) |
| `FOOTBALL_DATA_API_KEY` | Python | register free at football-data.org |

Put real values in `.env` (gitignored). For Vercel, set `DATABASE_URL` in
project env vars. For GitHub Actions, set both as repo secrets.

**The author will create accounts and supply keys themselves** — do not attempt
to register services or commit secrets.

---

## 9. Definition of done (v1)

- [ ] Neon schema applied
- [ ] EPL RESULT model trains and writes predictions for upcoming fixtures
- [ ] World Cup RESULT predictions for the current knockout round
- [ ] `daily_runner` runs end-to-end locally and is idempotent
- [ ] Grading writes Brier + correctness for finished fixtures
- [ ] Next.js app shows fixtures + predictions + confidence, with league toggle
- [ ] Accuracy scoreboard reads from `grades` and renders per-market accuracy
- [ ] GitHub Actions daily cron green
- [ ] README with architecture diagram + live accuracy table

Stretch: scoreline-as-Poisson with O/U + BTTS derived; calibration-by-confidence
chart; model versioning surfaced in the UI.
