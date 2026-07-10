# Footy Oracle

A self-running soccer match-prediction system. It ingests data daily, predicts
upcoming fixtures across four betting-style markets, and **grades its own
predictions against real results** — showing live accuracy and Brier-score
calibration on a public scoreboard.

**Live:** [your-app.vercel.app](https://your-app.vercel.app)

---

## Architecture

```
┌─ Python (offline brain) ─ GitHub Actions cron ─────────────────┐
│  scripts/daily_runner.py                                        │
│   1. ingest   EPL (Understat xG + football-data.org)            │
│               World Cup (football-data.org)                     │
│   2. features Elo + rolling form + xG (EPL only)                │
│   3. predict  upcoming fixtures × 4 markets (XGBoost + Poisson) │
│   4. grade    finished fixtures → correct + Brier score         │
│        │ writes via psycopg2                                     │
│        ▼                                                        │
│   ┌──────────────┐                                              │
└───│ Neon Postgres │──────────────────────────────────────────────┘
    └──────────────┘
        │ reads via @neondatabase/serverless
┌─ Next.js (App Router) on Vercel ───────────────────────────────┐
│   /api/predictions  → upcoming fixtures + market probabilities  │
│   /api/accuracy     → scoreboard aggregates from grades table   │
│   /                 → fixture cards, confidence bars, scoreboard│
└────────────────────────────────────────────────────────────────┘
```

**Markets predicted per fixture:**
| Market | Model | Labels |
|---|---|---|
| Result | XGBoost multiclass | home / draw / away |
| O/U 2.5 goals | Poisson (derived) | over / under |
| Both teams score | Poisson (derived) | yes / no |
| Scoreline | Poisson bivariate | 0-0 … 6-6 |

---

## Accuracy Scoreboard

| Market | Graded | Accuracy | Avg Brier |
|---|---|---|---|
| Result | — | — | — |
| O/U 2.5 | — | — | — |
| BTTS | — | — | — |
| Scoreline | — | — | — |

*Auto-updated daily. Brier score measures calibration — lower is better (0 = perfect, 2 = worst).*

---

## Setup

### Prerequisites
- Python 3.11+
- Node 20+
- [Neon](https://neon.tech) free Postgres project
- [football-data.org](https://www.football-data.org) free API key

### 1. Clone and install

```bash
git clone <your-repo>
cd footy-oracle

# Python
pip install -r requirements.txt

# Node (web app)
cd web && npm install
```

### 2. Environment variables

```bash
cp .env.example .env
# Edit .env — add DATABASE_URL and FOOTBALL_DATA_API_KEY
```

### 3. Apply schema

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
from pipeline.db import get_conn, init_schema
conn = get_conn()
init_schema(conn)
conn.close()
print('Schema applied.')
"
```

### 4. Backfill history and train models

```bash
python scripts/backfill.py
```

This loads 3 EPL seasons from Understat, trains XGBoost + Poisson models, and
writes predictions for all upcoming fixtures.

### 5. Run the web app locally

```bash
cd web
# Create web/.env.local with DATABASE_URL
npm run dev
```

### 6. Deploy

- **Vercel:** import the `web/` directory, set `DATABASE_URL` in project settings.
- **GitHub Actions:** set `DATABASE_URL` and `FOOTBALL_DATA_API_KEY` as repo secrets.
  The daily cron runs at 06:00 UTC.

---

## Modeling notes

- **Leak-safe features.** Elo and rolling form only update on finished matches,
  so upcoming fixtures never see future information.
- **EPL vs World Cup honesty.** EPL has rich shot-level xG from Understat; the
  World Cup model is deliberately limited to Elo + form (no free xG source for
  international football). The calibration difference shows up honestly in the
  scoreboard — that's a feature, not a bug.
- **Scoreline as base.** O/U 2.5 and BTTS are derived from the Poisson
  scoreline distribution rather than trained as separate classifiers — this
  keeps them coherent (a high-xG match can't simultaneously be predicted as
  low-scoring on O/U but yes on BTTS).

---

## Project layout

```
footy-oracle/
├── db/schema.sql              # fixtures, predictions, grades
├── pipeline/
│   ├── league.py              # League abstraction (EPL / WORLD_CUP)
│   ├── db.py                  # psycopg2 helpers
│   ├── ingest/
│   │   ├── football_data.py   # fixtures + results
│   │   └── understat.py       # EPL xG
│   ├── features/build.py      # Elo + rolling form, leak-safe
│   ├── models/
│   │   ├── result.py          # XGBoost multiclass
│   │   ├── scoreline.py       # Poisson bivariate
│   │   ├── over_under.py      # derived from scoreline
│   │   └── btts.py            # derived from scoreline
│   └── eval/grade.py          # Brier + correctness grading
├── scripts/
│   ├── backfill.py            # one-off history load + train
│   └── daily_runner.py        # daily ingest → predict → grade
├── web/                       # Next.js app (Vercel)
│   ├── app/page.tsx           # main UI
│   ├── app/api/predictions/   # upcoming fixtures + probs
│   ├── app/api/accuracy/      # scoreboard data
│   └── lib/db.ts              # Neon client
└── .github/workflows/
    ├── daily.yml              # cron pipeline
    └── ci.yml                 # lint + type-check + build
```
