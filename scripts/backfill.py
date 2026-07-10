"""
One-shot historical backfill + initial model training.

Run from the project root after setting DATABASE_URL and FOOTBALL_DATA_API_KEY:
    python scripts/backfill.py

What it does:
  1. Apply DB schema (idempotent).
  2. EPL: pull Understat xG for recent seasons → reconstruct match history →
     upsert fixtures → build features → train result + scoreline models →
     predict upcoming fixtures.
  3. World Cup 2026: pull all matches from football-data.org → upsert →
     build features → train models → predict scheduled fixtures.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import pandas as pd

from pipeline.db import get_conn, init_schema, upsert_fixture, upsert_prediction
from pipeline.features.build import build_features
from pipeline.ingest.football_data import fetch_fixtures
from pipeline.ingest.understat import fetch_epl_xg
from pipeline.league import EPL, WORLD_CUP
from pipeline.models import moe

MODEL_VERSION = "v1"
EPL_SEASONS = [2022, 2023, 2024]  # Understat seasons (year = season start)
WC_SEASON = "2026"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upsert_and_map(conn, fixtures: list[dict]) -> dict:
    """Upsert fixtures and return {source_match_id: fixture_id}."""
    id_map = {}
    for fx in fixtures:
        fid = upsert_fixture(conn, fx)
        id_map[fx["source_match_id"]] = fid
    return id_map


def _write_predictions(conn, upcoming_ids: list[int], league,
                       result_probs: list[dict], result_experts: list[str],
                       scoreline_probs: list[dict], scoreline_experts: list[str],
                       ou_probs: list[dict], btts_probs: list[dict]) -> None:
    for i, fid in enumerate(upcoming_ids):
        _upsert_pred(conn, fid, "RESULT", result_probs[i], MODEL_VERSION, result_experts[i])
        _upsert_pred(conn, fid, "SCORELINE", scoreline_probs[i], MODEL_VERSION, scoreline_experts[i])
        _upsert_pred(conn, fid, "OVER_UNDER_2_5", ou_probs[i], MODEL_VERSION, scoreline_experts[i])
        _upsert_pred(conn, fid, "BTTS", btts_probs[i], MODEL_VERSION, scoreline_experts[i])


def _upsert_pred(conn, fixture_id: int, market: str, probs: dict,
                 model_version: str, expert_used: str | None = None) -> None:
    predicted = max(probs, key=probs.get)
    confidence = probs[predicted]
    upsert_prediction(conn, {
        "fixture_id": fixture_id,
        "market": market,
        "probs": probs,
        "predicted": predicted,
        "confidence": confidence,
        "model_version": model_version,
        "expert_used": expert_used,
    })


# ---------------------------------------------------------------------------
# EPL
# ---------------------------------------------------------------------------

def _build_xg_lookup(xg_rows: list[dict]) -> dict:
    """Build {(date_str, team): {"xgf": x, "xga": x}} from Understat rows."""
    lookup = {}
    for row in xg_rows:
        date_str = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
        lookup[(date_str, row["team"])] = {"xgf": row["xg"], "xga": row["opp_xg"]}
    return lookup


def _understat_to_matches(xg_rows: list[dict]) -> pd.DataFrame:
    """Reconstruct per-match rows from Understat per-team rows."""
    df = pd.DataFrame(xg_rows)
    df["date_only"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    home = df[df["is_home"] == 1][["match", "date_only", "team", "goals"]].copy()
    home = home.rename(columns={"team": "home_team", "goals": "home_goals"})
    away = df[df["is_home"] == 0][["match", "team", "goals"]].copy()
    away = away.rename(columns={"team": "away_team", "goals": "away_goals"})
    matches = home.merge(away, on="match")
    matches = matches.rename(columns={"date_only": "date"})
    matches["neutral"] = False
    return matches[["date", "home_team", "away_team", "home_goals", "away_goals", "neutral"]]


def _fetch_epl_history_fallback() -> tuple:
    """Pull EPL history from football-data.org when Understat is unavailable."""
    print("  Falling back to football-data.org for EPL history...")
    all_matches: list[dict] = []
    for season_year in EPL_SEASONS:
        try:
            fixtures = fetch_fixtures("EPL", season=str(season_year))
            finished = [f for f in fixtures
                        if f["status"] == "FINISHED" and f["home_goals"] is not None]
            all_matches.extend(finished)
            print(f"    football-data.org {season_year}/{season_year+1}: {len(finished)} matches")
        except Exception as e:
            print(f"    WARNING season {season_year}: {e}")

    if not all_matches:
        return None, {}

    df = pd.DataFrame([{
        "date": f["kickoff_utc"][:10],
        "home_team": f["home_team"],
        "away_team": f["away_team"],
        "home_goals": f["home_goals"],
        "away_goals": f["away_goals"],
        "neutral": False,
    } for f in all_matches])
    return df, {}   # no xg_lookup when using this fallback


def backfill_epl(conn) -> None:
    print("\n=== EPL backfill ===")
    all_xg: list[dict] = []
    for season in EPL_SEASONS:
        print(f"  Understat {season}/{season + 1}...")
        try:
            rows = fetch_epl_xg(season)
            all_xg.extend(rows)
            print(f"    {len(rows)//2} matches")
        except Exception as e:
            print(f"    WARNING: {e}")

    if all_xg:
        xg_lookup = _build_xg_lookup(all_xg)
        hist_df = _understat_to_matches(all_xg).drop_duplicates(
            subset=["date", "home_team", "away_team"]
        )
    else:
        hist_df, xg_lookup = _fetch_epl_history_fallback()
        if hist_df is None:
            print("  No EPL history available — skipping EPL training.")
            return

    # upcoming fixtures from football-data.org
    print("  Fetching EPL scheduled fixtures...")
    try:
        upcoming_raw = [f for f in fetch_fixtures("EPL") if f["status"] == "SCHEDULED"]
    except Exception as e:
        print(f"  WARNING: {e}")
        upcoming_raw = []

    # upsert historical + upcoming fixtures
    for fx in _hist_to_fixture_dicts(hist_df):
        upsert_fixture(conn, fx)

    id_map = _upsert_and_map(conn, upcoming_raw)

    # build feature matrix (history + upcoming)
    upcoming_df = pd.DataFrame([{
        "date": f["kickoff_utc"][:10],
        "home_team": f["home_team"],
        "away_team": f["away_team"],
        "home_goals": None,
        "away_goals": None,
        "neutral": False,
    } for f in upcoming_raw])

    all_matches = pd.concat([hist_df, upcoming_df], ignore_index=True) if not upcoming_df.empty else hist_df
    feat_df = build_features(all_matches, EPL, xg_lookup)

    print("  Training EPL MoE experts...")
    moe.train(feat_df, EPL)

    if upcoming_raw:
        upcom_feat = feat_df[feat_df["home_goals"].isna()].reset_index(drop=True)
        upcoming_ids = [id_map[f["source_match_id"]] for f in upcoming_raw
                        if f["source_match_id"] in id_map]

        if len(upcom_feat) == len(upcoming_ids):
            r_probs, r_experts = moe.predict_result(upcom_feat, EPL)
            s_probs, s_experts = moe.predict_scoreline(upcom_feat, EPL)
            o_probs = moe.predict_over_under(upcom_feat, EPL)
            b_probs = moe.predict_btts(upcom_feat, EPL)
            _write_predictions(conn, upcoming_ids, EPL,
                               r_probs, r_experts, s_probs, s_experts, o_probs, b_probs)
            print(f"  Wrote predictions for {len(upcoming_ids)} EPL fixtures.")


def _hist_to_fixture_dicts(df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "league": "EPL",
            "source_match_id": f"us_{r['date']}_{r['home_team']}_{r['away_team']}",
            "season": str(r["date"])[:4],
            "kickoff_utc": f"{r['date']}T15:00:00Z",
            "home_team": r["home_team"],
            "away_team": r["away_team"],
            "stage": "LEAGUE",
            "home_goals": None if pd.isna(r["home_goals"]) else int(r["home_goals"]),
            "away_goals": None if pd.isna(r["away_goals"]) else int(r["away_goals"]),
            "status": "FINISHED",
        })
    return rows


# ---------------------------------------------------------------------------
# World Cup 2026
# ---------------------------------------------------------------------------

def backfill_wc(conn) -> None:
    print("\n=== World Cup 2026 backfill ===")
    print("  Fetching WC fixtures from football-data.org...")
    try:
        all_raw = fetch_fixtures("WORLD_CUP")
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    id_map = _upsert_and_map(conn, all_raw)
    print(f"  Upserted {len(all_raw)} WC fixtures.")

    matches_df = pd.DataFrame([{
        "date": f["kickoff_utc"][:10],
        "home_team": f["home_team"],
        "away_team": f["away_team"],
        "home_goals": f["home_goals"],
        "away_goals": f["away_goals"],
        "neutral": True,
        "stage": f.get("stage", "GROUP_STAGE"),
    } for f in all_raw])

    feat_df = build_features(matches_df, WORLD_CUP)
    # carry stage through for MoE routing (not a model feature)
    stage_map = {
        (f["kickoff_utc"][:10], f["home_team"], f["away_team"]): f.get("stage")
        for f in all_raw
    }
    feat_df["stage"] = feat_df.apply(
        lambda r: stage_map.get((str(r["date"].date()), r["home_team"], r["away_team"])),
        axis=1,
    )

    finished_count = matches_df["home_goals"].notna().sum()
    if finished_count < 10:
        print(f"  Only {finished_count} finished WC matches — skipping training.")
        return

    print("  Training WC MoE experts...")
    moe.train(feat_df, WORLD_CUP)

    upcoming_raw = [f for f in all_raw if f["status"] == "SCHEDULED"]
    if not upcoming_raw:
        print("  No upcoming WC fixtures to predict.")
        return

    upcom_feat = feat_df[feat_df["home_goals"].isna()].reset_index(drop=True)
    upcoming_valid = [f for f in upcoming_raw if f["source_match_id"] in id_map]
    upcoming_ids = [id_map[f["source_match_id"]] for f in upcoming_valid]
    upcoming_stages = [f.get("stage") for f in upcoming_valid]

    if len(upcom_feat) == len(upcoming_ids):
        r_probs, r_experts = moe.predict_result(upcom_feat, WORLD_CUP, upcoming_stages)
        s_probs, s_experts = moe.predict_scoreline(upcom_feat, WORLD_CUP, upcoming_stages)
        o_probs = moe.predict_over_under(upcom_feat, WORLD_CUP, upcoming_stages)
        b_probs = moe.predict_btts(upcom_feat, WORLD_CUP, upcoming_stages)
        _write_predictions(conn, upcoming_ids, WORLD_CUP,
                           r_probs, r_experts, s_probs, s_experts, o_probs, b_probs)
        print(f"  Wrote predictions for {len(upcoming_ids)} WC fixtures.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    conn = get_conn()
    print("Connected to Neon Postgres.")
    init_schema(conn, os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql"))
    print("Schema applied.")

    backfill_epl(conn)
    backfill_wc(conn)
    conn.close()
    print("\nBackfill complete.")


if __name__ == "__main__":
    main()
