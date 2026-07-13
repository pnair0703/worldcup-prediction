# footy-oracle — Architecture & Build Handoff

A self-running soccer match-prediction system. It ingests data daily, predicts
upcoming fixtures across several betting-style markets, serves those predictions
through a serverless web app, and **grades its own predictions against real
results over time** — the headline feature.

It runs **two competitions through one engine**:
- **EPL** — the durable flagship. Rich shot-level xG data, runs year-round.
- **World Cup 2026** — a live "skin" on the same engine while the tournament is
  on (ends July 19, 2026). Thin international data, so it leans on Elo + form.
- **EPL 2026/27** — upcoming season tab, same EPL engine, filtered by `season='2026'`.

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

Anti-goals: don't call any upstream API's pre-baked predictions (e.g. some
free football APIs ship their own CatBoost predictions — never use those, we
BUILD the model); don't merge Python into the request path. The chatbot is a
thin UI layer that reads the database — it doesn't produce predictions.

---

## 2. Architecture

```
┌─ Python (offline brain) ─ runs on GitHub Actions cron ─────────┐
│  scripts/daily_runner.py orchestrates:                         │
│   1. ingest  EPL (Understat xG + football-data.org fixtures)   │
│              World Cup (football-data.org only)                │
│   2. features (Elo + rolling form, + xG when available)        │
│   3. predict  via MoE coordinator (pipeline/models/moe.py)     │
│              EPL:  full_expert + recent_expert (soft-routed)   │
│              WC:   group_expert + knockout_expert (hard-routed) │
│   4. grade  yesterday's now-finished fixtures vs reality       │
│        │ writes via psycopg2                                   │
│        ▼                                                       │
│   ┌──────────────┐                                             │
└───│ Neon Postgres │─────────────────────────────────────────────┘
    └──────────────┘
        │ reads via @neondatabase/serverless
┌─ Node (online serving + UI) ─ Next.js on Vercel ──────────────┐
│   app/api/predictions  → upcoming fixtures + market probs     │
│   app/api/accuracy     → scoreboard aggregates                │
│   app/api/chat         → Groq streaming chatbot (edge fn)     │
│                           reads DB via 4 tools; no own preds  │
│   app/ (React)         → fixtures, confidence bars,           │
│                           EPL / EPL 2026/27 / WC toggle,      │
│                           accuracy scoreboard, chat widget     │
└────────────────────────────────────────────────────────────────┘
                                    │ LLM calls (streaming)
                              ┌─────▼──────┐
                              │  Groq API  │  llama-3.3-70b-versatile
                              │ (free tier)│  500K tokens/day
                              └────────────┘
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
| MoE coordinator | `pipeline/models/moe.py`    | soft-routes EPL experts; hard-routes WC experts by stage |
| Store        | **Neon Postgres**               | serverless PG; Python writes, Node reads |
| Serving + UI | **Next.js (App Router) on Vercel** | serverless API routes + React |
| DB driver (Node) | `@neondatabase/serverless`  | HTTP driver; also works on edge runtime for chatbot tools |
| Chatbot LLM  | **Groq** (`llama-3.3-70b-versatile`) | free tier, 500K tokens/day; streaming via Vercel AI SDK |
| AI SDK       | `ai` + `@ai-sdk/groq`           | `streamText` + `useChat`; edge-compatible |
| Scheduler    | **GitHub Actions cron**         | runs `daily_runner.py` daily |

---

## 4. Repository layout

```
workout-prediction/
├── ARCHITECTURE.md            # this file
├── README.md
├── .env.example               # DATABASE_URL, FOOTBALL_DATA_API_KEY, GROQ_API_KEY
├── db/
│   └── schema.sql             # DONE: fixtures, predictions (+ expert_used), grades
├── pipeline/
│   ├── league.py              # DONE: League abstraction (EPL has xG, WC doesn't)
│   ├── db.py                  # DONE: psycopg2 helpers; upsert_prediction includes expert_used
│   ├── ingest/
│   │   ├── football_data.py   # DONE: EPL + WC fixtures/results
│   │   └── understat.py       # DONE: EPL shot-level xG
│   ├── features/
│   │   └── build.py           # DONE: Elo + rolling form/xG, leak-safe
│   ├── models/
│   │   ├── moe.py             # DONE: MoE coordinator — see §7a
│   │   ├── result.py          # DONE: XGBoost multiclass; expert param selects model file
│   │   ├── over_under.py      # DONE: O/U 2.5 (derived from Poisson scoreline)
│   │   ├── btts.py            # DONE: BTTS (derived from Poisson scoreline)
│   │   └── scoreline.py       # DONE: Bivariate Poisson; expert param selects model file
│   └── eval/
│       └── grade.py           # DONE: grade finished predictions, write Brier
├── scripts/
│   ├── daily_runner.py        # DONE: ingest→features→predict(MoE)→grade; idempotent
│   └── backfill.py            # DONE: historical load + initial MoE train
├── web/                       # Next.js on Vercel
│   ├── package.json           # ai, @ai-sdk/groq, zod added
│   ├── app/
│   │   ├── page.tsx           # fixtures UI; handles EPL_2026 tab → season=2026 param
│   │   ├── api/
│   │   │   ├── predictions/route.ts  # ?league= &season= filtering
│   │   │   ├── accuracy/route.ts
│   │   │   └── chat/route.ts         # DONE: Groq streaming, edge runtime, 4 DB tools
│   │   └── components/
│   │       ├── ChatWidget.tsx        # DONE: floating ⚽ button + chat panel
│   │       ├── FixtureCard.tsx       # resolves "home"/"away" → actual team names
│   │       ├── ConfidenceBar.tsx     # teamNames prop for RESULT bars
│   │       ├── LeagueToggle.tsx      # EPL | EPL 2026/27 | World Cup 2026
│   │       └── Scoreboard.tsx
│   └── lib/db.ts              # Neon serverless client (HTTP, edge-safe)
├── .github/workflows/
│   ├── daily.yml              # cron → daily_runner
│   └── ci.yml                 # lint + import smoke test (includes moe)
└── requirements.txt
```

### What already exists (read these first, build on them)
- `db/schema.sql` — the three tables. Predictions store `probs` as JSONB so each
  market carries its own label set. `grades` powers the scoreboard.
  `predictions.expert_used TEXT` records which MoE expert produced each prediction.
- `pipeline/league.py` — the `League` dataclass. Models train on exactly
  `League.feature_columns`. Adding a competition = new ingester + new League.
- `pipeline/db.py` — `get_conn`, `init_schema`, `upsert_fixture`,
  `upsert_prediction` (now accepts `expert_used`), `upsert_grade`, `fetch_finished_ungraded`.
- `pipeline/ingest/football_data.py` — `fetch_fixtures(league, date_from, date_to)`
  returns normalized fixture dicts. Reads `FOOTBALL_DATA_API_KEY`.
- `pipeline/ingest/understat.py` — `fetch_epl_xg(season)` returns per-team,
  per-match xG rows for building rolling features.
- `pipeline/features/build.py` — `build_features(matches_df, league, xg_lookup)`.
  Elo with home-adv + margin-of-victory; rolling form. **Leak-safe**: state only
  updates on finished matches, so upcoming fixtures see only past info. Preserve
  this property in anything you add.
- `pipeline/models/moe.py` — MoE coordinator. Call `moe.train(df, league)` and
  `moe.predict_result(df, league, stages)` etc. from scripts; don't call individual
  model files directly from scripts anymore.

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
- **Scoreline** is a Bivariate Poisson model: predict home/away expected goals,
  derive a scoreline distribution. O/U and BTTS are derived from the same
  distribution by summing cells — stronger and more coherent than separate heads.
- **EPL vs WC honesty.** WC has no xG and little history — lean on Elo + recent
  international form, report calibration honestly, don't fake xG. The scoreboard
  will (correctly) show WC predictions as less sharp; that's a feature, not a bug.
- **Leakage.** `build.py` only updates Elo/form on FINISHED matches. Any new
  feature must respect this — never let an upcoming fixture see its own result or
  future matches.

### 7a. Mixture-of-Experts (MoE)

`pipeline/models/moe.py` is the single entry point for training and inference.
Never call `result.py` or `scoreline.py` directly from scripts.

**EPL — soft routing** on `|elo_diff|`:

| Expert | Trained on | Weight formula |
|--------|-----------|----------------|
| `full` | all 4 historical seasons | `w = 0.3 + 0.4 × clamp((gap−50)/200, 0, 1)` |
| `recent` | last 2 seasons (≥730 days from last finished match) | `1 − w` |

When |elo_diff| < 50, both experts contribute equally (w≈0.3/0.7 toward recent).
When |elo_diff| > 250, the full expert dominates (w=0.7). Minimum 20 finished
matches required to train recent_expert; falls back to full_expert only if not met.

**WC — hard routing** on the fixture's `stage` field:

| Expert | Stage keywords | Fallback |
|--------|---------------|---------|
| `group` | anything not in knockout list | — |
| `knockout` | ROUND_OF, QUARTER, SEMI, FINAL, PLAYOFF, KNOCKOUT | combined model if < 20 samples |

Both leagues also train a combined model (no expert suffix) as the fallback base.

**Model files** are saved as `result_{LEAGUE}_{expert}_v1.joblib`, e.g.:
- `result_EPL_full_v1.joblib`, `result_EPL_recent_v1.joblib`, `result_EPL_v1.joblib`
- `result_WORLD_CUP_group_v1.joblib`, `result_WORLD_CUP_v1.joblib`

**Key implementation note:** the recent_expert cutoff is computed from
`finished_dates.max()` (not `df["date"].max()`). Using all dates skews the max
into the future (upcoming fixtures have future dates), shrinking the recent window
incorrectly.

**`expert_used`** is written to `predictions.expert_used` per row so the chatbot
and the UI can surface which expert produced each prediction.

---

## 8. Environment variables

| Var | Used by | How to get |
|-----|---------|-----------|
| `DATABASE_URL` | Python + Node | Neon project → Connection string (free tier) |
| `FOOTBALL_DATA_API_KEY` | Python | register free at football-data.org |
| `GROQ_API_KEY` | Node (chatbot) | console.groq.com → API Keys (free, 500K tokens/day) |

Put real values in `.env` (gitignored). Set all three in Vercel project env vars
and as GitHub Actions repo secrets.

**The author will create accounts and supply keys themselves** — do not attempt
to register services or commit secrets.

> **Security:** Never commit `.env` to git. If credentials are accidentally
> committed, rotate them immediately: reset the Neon DB password, regenerate the
> football-data.org API key, and regenerate the Groq API key. Then update Vercel
> env vars and GitHub secrets with the new values.

---

## 9. Definition of done

### v1 — core pipeline ✅
- [x] Neon schema applied (fixtures, predictions, grades + `expert_used`)
- [x] EPL RESULT model trains and writes predictions for upcoming fixtures
- [x] World Cup RESULT predictions for the current knockout round
- [x] `daily_runner` runs end-to-end locally and is idempotent
- [x] Grading writes Brier + correctness for finished fixtures
- [x] Next.js app shows fixtures + predictions + confidence bars
- [x] Team names shown in RESULT bars (not raw "home"/"away" labels)
- [x] League toggle: Premier League | EPL 2026/27 | World Cup 2026
- [x] Accuracy scoreboard reads from `grades` and renders per-market accuracy
- [x] GitHub Actions daily cron green

### v2 — MoE + chatbot ✅
- [x] Bivariate Poisson scoreline model; O/U 2.5 + BTTS derived from same distribution
- [x] MoE coordinator (`moe.py`): soft-routing for EPL, hard-routing for WC
- [x] `expert_used` recorded per prediction in DB
- [x] Groq chatbot with 4 DB-backed tools (predictions, form, accuracy, explain)
- [x] ChatWidget floating UI with example prompts
- [x] EPL 2026/27 season tab (filters by `season='2026'`)

### Remaining / stretch
- [ ] Credentials rotated after accidental git commit (Neon PW + football-data key + Groq key)
- [ ] Predictions API 500 error investigated and fixed (Vercel function logs)
- [ ] Calibration-by-confidence chart
- [ ] README with architecture diagram + live accuracy table
- [ ] Model versioning surfaced in UI
