"""
Grade finished predictions against actual results.

Writes correct (bool) + multiclass Brier score for every ungraded prediction
whose fixture is now FINISHED.
"""
import json

from ..db import fetch_finished_ungraded, upsert_grade


def _actual(home_goals: int, away_goals: int, market: str) -> str:
    if market == "RESULT":
        if home_goals > away_goals:
            return "home"
        if away_goals > home_goals:
            return "away"
        return "draw"
    if market == "OVER_UNDER_2_5":
        return "over" if (home_goals + away_goals) > 2 else "under"
    if market == "BTTS":
        return "yes" if (home_goals > 0 and away_goals > 0) else "no"
    if market == "SCORELINE":
        return f"{home_goals}-{away_goals}"
    raise ValueError(f"Unknown market: {market}")


def _brier(probs: dict, actual: str) -> float:
    return sum((p - (1.0 if cls == actual else 0.0)) ** 2 for cls, p in probs.items())


def grade_league(conn, league_key: str) -> int:
    rows = fetch_finished_ungraded(conn, league_key)
    for row in rows:
        probs = row["probs"] if isinstance(row["probs"], dict) else json.loads(row["probs"])
        actual = _actual(int(row["home_goals"]), int(row["away_goals"]), row["market"])
        upsert_grade(conn, {
            "prediction_id": row["prediction_id"],
            "fixture_id": row["fixture_id"],
            "league": row["league"],
            "market": row["market"],
            "actual": actual,
            "correct": row["predicted"] == actual,
            "brier": _brier(probs, actual),
        })
    return len(rows)
