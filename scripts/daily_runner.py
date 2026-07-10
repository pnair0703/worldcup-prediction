"""
Daily pipeline: ingest → features → predict → grade.

Idempotent: all writes are upserts; safe to run multiple times per day.
Run from the project root:
    python scripts/daily_runner.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import pandas as pd

from pipeline.db import get_conn, upsert_fixture, upsert_prediction
from pipeline.eval.grade import grade_league
from pipeline.features.build import build_features
from pipeline.ingest.football_data import fetch_fixtures, utc_now_iso
from pipeline.ingest.understat import fetch_epl_xg
from pipeline.league import EPL, WORLD_CUP
from pipeline.models import result as result_model
from pipeline.models import scoreline as scoreline_model

MODEL_VERSION = "v1"
INGEST_WINDOW_DAYS = 10   # fetch ±10 days around today
EPL_CURRENT_SEASON = 2024  # Understat season for current EPL xG


def _date_window():
    today = datetime.now(timezone.utc)
    return (
        (today - timedelta(days=INGEST_WINDOW_DAYS)).strftime("%Y-%m-%d"),
        (today + timedelta(days=INGEST_WINDOW_DAYS)).strftime("%Y-%m-%d"),
    )


def _upsert_pred(conn, fixture_id: int, market: str, probs: dict) -> None:
    predicted = max(probs, key=probs.get)
    upsert_prediction(conn, {
        "fixture_id": fixture_id,
        "market": market,
        "probs": probs,
        "predicted": predicted,
        "confidence": probs[predicted],
        "model_version": MODEL_VERSION,
    })


# ---------------------------------------------------------------------------
# EPL daily run
# ---------------------------------------------------------------------------

def run_epl(conn) -> None:
    print("\n--- EPL ---")
    date_from, date_to = _date_window()

    # 1. ingest recent window
    try:
        fixtures_raw = fetch_fixtures("EPL", date_from, date_to)
    except Exception as e:
        print(f"  ingest error: {e}")
        return

    id_map = {}
    for fx in fixtures_raw:
        fid = upsert_fixture(conn, fx)
        id_map[fx["source_match_id"]] = fid
    print(f"  upserted {len(fixtures_raw)} fixtures")

    if not result_model.model_exists("EPL"):
        print("  No EPL model found — run scripts/backfill.py first.")
        return

    # 2. pull current-season xG for rolling features
    try:
        xg_rows = fetch_epl_xg(EPL_CURRENT_SEASON)
        xg_lookup = {
            (pd.to_datetime(r["date"]).strftime("%Y-%m-%d"), r["team"]): {
                "xgf": r["xg"], "xga": r["opp_xg"]
            }
            for r in xg_rows
        }
    except Exception as e:
        print(f"  xG fetch error (using goals as fallback): {e}")
        xg_rows, xg_lookup = [], {}

    # 3. build feature matrix for window
    matches_df = pd.DataFrame([{
        "date": f["kickoff_utc"][:10],
        "home_team": f["home_team"],
        "away_team": f["away_team"],
        "home_goals": f["home_goals"],
        "away_goals": f["away_goals"],
        "neutral": False,
    } for f in fixtures_raw])

    feat_df = build_features(matches_df, EPL, xg_lookup or None)

    # 4. predict scheduled fixtures
    upcoming_raw = [f for f in fixtures_raw if f["status"] == "SCHEDULED"]
    upcom_feat = feat_df[feat_df["home_goals"].isna()].reset_index(drop=True)
    upcoming_ids = [id_map[f["source_match_id"]] for f in upcoming_raw
                    if f["source_match_id"] in id_map]

    if upcoming_ids and len(upcom_feat) == len(upcoming_ids):
        r_probs = result_model.predict_proba(upcom_feat, EPL)
        s_probs = scoreline_model.predict_scoreline(upcom_feat, EPL)
        o_probs = scoreline_model.predict_over_under(upcom_feat, EPL)
        b_probs = scoreline_model.predict_btts(upcom_feat, EPL)
        for i, fid in enumerate(upcoming_ids):
            _upsert_pred(conn, fid, "RESULT", r_probs[i])
            _upsert_pred(conn, fid, "SCORELINE", s_probs[i])
            _upsert_pred(conn, fid, "OVER_UNDER_2_5", o_probs[i])
            _upsert_pred(conn, fid, "BTTS", b_probs[i])
        print(f"  predicted {len(upcoming_ids)} upcoming fixtures")
    else:
        print(f"  no upcoming EPL fixtures in window")

    # 5. grade finished predictions
    n = grade_league(conn, "EPL")
    print(f"  graded {n} predictions")


# ---------------------------------------------------------------------------
# World Cup daily run
# ---------------------------------------------------------------------------

def run_wc(conn) -> None:
    print("\n--- World Cup 2026 ---")
    date_from, date_to = _date_window()

    try:
        fixtures_raw = fetch_fixtures("WORLD_CUP", date_from, date_to)
    except Exception as e:
        print(f"  ingest error: {e}")
        return

    id_map = {}
    for fx in fixtures_raw:
        fid = upsert_fixture(conn, fx)
        id_map[fx["source_match_id"]] = fid
    print(f"  upserted {len(fixtures_raw)} fixtures")

    if not result_model.model_exists("WORLD_CUP"):
        print("  No WC model found — run scripts/backfill.py first.")
        return

    matches_df = pd.DataFrame([{
        "date": f["kickoff_utc"][:10],
        "home_team": f["home_team"],
        "away_team": f["away_team"],
        "home_goals": f["home_goals"],
        "away_goals": f["away_goals"],
        "neutral": True,
    } for f in fixtures_raw])

    feat_df = build_features(matches_df, WORLD_CUP)
    upcoming_raw = [f for f in fixtures_raw if f["status"] == "SCHEDULED"]
    upcom_feat = feat_df[feat_df["home_goals"].isna()].reset_index(drop=True)
    upcoming_ids = [id_map[f["source_match_id"]] for f in upcoming_raw
                    if f["source_match_id"] in id_map]

    if upcoming_ids and len(upcom_feat) == len(upcoming_ids):
        r_probs = result_model.predict_proba(upcom_feat, WORLD_CUP)
        s_probs = scoreline_model.predict_scoreline(upcom_feat, WORLD_CUP)
        o_probs = scoreline_model.predict_over_under(upcom_feat, WORLD_CUP)
        b_probs = scoreline_model.predict_btts(upcom_feat, WORLD_CUP)
        for i, fid in enumerate(upcoming_ids):
            _upsert_pred(conn, fid, "RESULT", r_probs[i])
            _upsert_pred(conn, fid, "SCORELINE", s_probs[i])
            _upsert_pred(conn, fid, "OVER_UNDER_2_5", o_probs[i])
            _upsert_pred(conn, fid, "BTTS", b_probs[i])
        print(f"  predicted {len(upcoming_ids)} upcoming fixtures")
    else:
        print(f"  no upcoming WC fixtures in window")

    n = grade_league(conn, "WORLD_CUP")
    print(f"  graded {n} predictions")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"[daily_runner] {utc_now_iso()} UTC")
    conn = get_conn()
    run_epl(conn)
    run_wc(conn)
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
