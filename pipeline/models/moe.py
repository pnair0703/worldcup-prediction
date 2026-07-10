"""
Mixture-of-Experts coordinator.

EPL  — two experts:
  · full_expert   trained on all 3 seasons  (better long-run Elo calibration)
  · recent_expert trained on latest 2 seasons (stronger form signal)
  Soft routing on |elo_diff|: large mismatch → full_expert; close game → recent_expert.
  Intuition: when teams are evenly matched on Elo, recent form is the tiebreaker.

WC   — two experts:
  · group_expert    trained on group-stage matches (higher scoring, draws common)
  · knockout_expert trained on knockout matches (tight, low-scoring, Elo decisive)
  Hard routing via the fixture stage field; falls back to combined model if an
  expert has fewer than MIN_SAMPLES finished training matches.
"""
from __future__ import annotations

import pandas as pd

from . import result as result_model
from . import scoreline as scoreline_model

FULL_EXPERT = "full"
RECENT_EXPERT = "recent"
GROUP_EXPERT = "group"
KNOCKOUT_EXPERT = "knockout"

MIN_SAMPLES = 20
RECENT_DAYS = 730  # ~2 seasons

_KNOCKOUT_KEYWORDS = ("ROUND_OF", "QUARTER", "SEMI", "FINAL", "PLAYOFF", "KNOCKOUT")


def _is_knockout(stage: str | None) -> bool:
    if not stage:
        return False
    s = stage.upper()
    return any(k in s for k in _KNOCKOUT_KEYWORDS)


def _epl_weights(elo_diff: float) -> tuple[float, float]:
    """
    Soft routing: |elo_diff| in [50, 250] maps w_full linearly from 0.3 → 0.7.
    Returns (w_full, w_recent).
    """
    gap = abs(elo_diff)
    w_full = 0.3 + 0.4 * min(max((gap - 50) / 200, 0.0), 1.0)
    return round(w_full, 3), round(1.0 - w_full, 3)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(df: pd.DataFrame, league) -> None:
    if league.key == "WORLD_CUP":
        _train_wc(df, league)
    else:
        _train_epl(df, league)


def _train_epl(df: pd.DataFrame, league) -> None:
    result_model.train(df, league, expert=FULL_EXPERT)
    scoreline_model.train(df, league, expert=FULL_EXPERT)
    print("  [moe] epl full_expert trained")

    df = df.copy()
    df["_dt"] = pd.to_datetime(df["date"])
    # base cutoff on the last FINISHED match, not upcoming fixtures which skew max date
    finished_dates = df.loc[df["home_goals"].notna(), "_dt"]
    cutoff = finished_dates.max() - pd.Timedelta(days=RECENT_DAYS)
    recent = df[df["_dt"] >= cutoff].drop(columns=["_dt"])
    recent_finished = len(recent.dropna(subset=["home_goals"]))

    if recent_finished >= MIN_SAMPLES:
        result_model.train(recent, league, expert=RECENT_EXPERT)
        scoreline_model.train(recent, league, expert=RECENT_EXPERT)
        print(f"  [moe] epl recent_expert trained on {recent_finished} rows")
    else:
        print(f"  [moe] epl recent_expert skipped ({recent_finished} finished rows in window)")

    result_model.train(df.drop(columns=["_dt"], errors="ignore"), league)
    scoreline_model.train(df.drop(columns=["_dt"], errors="ignore"), league)


def _train_wc(df: pd.DataFrame, league) -> None:
    if "stage" not in df.columns:
        print("  [moe] wc: no stage column — combined only")
        result_model.train(df, league)
        scoreline_model.train(df, league)
        return

    group_mask = ~df["stage"].apply(_is_knockout)
    group_df = df[group_mask]
    knockout_df = df[~group_mask]

    gf = len(group_df.dropna(subset=["home_goals"]))
    kf = len(knockout_df.dropna(subset=["home_goals"]))

    if gf >= MIN_SAMPLES:
        result_model.train(group_df, league, expert=GROUP_EXPERT)
        scoreline_model.train(group_df, league, expert=GROUP_EXPERT)
        print(f"  [moe] wc group_expert trained on {gf} rows")
    else:
        print(f"  [moe] wc group_expert skipped ({gf} rows)")

    if kf >= MIN_SAMPLES:
        result_model.train(knockout_df, league, expert=KNOCKOUT_EXPERT)
        scoreline_model.train(knockout_df, league, expert=KNOCKOUT_EXPERT)
        print(f"  [moe] wc knockout_expert trained on {kf} rows")
    else:
        print(f"  [moe] wc knockout_expert skipped ({kf} rows)")

    result_model.train(df, league)
    scoreline_model.train(df, league)


# ---------------------------------------------------------------------------
# Prediction helpers
# ---------------------------------------------------------------------------

def _blend_result(p_a: dict, p_b: dict, w_a: float, w_b: float) -> dict:
    blended = {k: w_a * p_a.get(k, 0) + w_b * p_b.get(k, 0) for k in p_a}
    total = sum(blended.values()) or 1
    return {k: round(v / total, 4) for k, v in blended.items()}


def _blend_scoreline(p_a: dict, p_b: dict, w_a: float, w_b: float) -> dict:
    all_keys = set(p_a) | set(p_b)
    blended = {k: w_a * p_a.get(k, 0) + w_b * p_b.get(k, 0) for k in all_keys}
    total = sum(blended.values()) or 1
    return {k: round(v / total, 5) for k, v in blended.items()}


# ---------------------------------------------------------------------------
# Public predict API
# ---------------------------------------------------------------------------

def predict_result(
    df: pd.DataFrame, league, stages: list[str | None] | None = None
) -> tuple[list[dict], list[str]]:
    """Returns (probs_list, expert_names_list)."""
    n = len(df)
    stages = list(stages) if stages else [None] * n

    if league.key == "WORLD_CUP":
        return _predict_wc_result(df, league, stages)
    return _predict_epl_result(df, league)


def _predict_epl_result(df: pd.DataFrame, league) -> tuple[list[dict], list[str]]:
    has_full = result_model.model_exists(league.key, FULL_EXPERT)
    has_recent = result_model.model_exists(league.key, RECENT_EXPERT)

    full_p = result_model.predict_proba(df, league, expert=FULL_EXPERT) if has_full \
        else result_model.predict_proba(df, league)
    recent_p = result_model.predict_proba(df, league, expert=RECENT_EXPERT) if has_recent \
        else full_p

    results, experts = [], []
    for i, (_, row) in enumerate(df.iterrows()):
        w_full, w_recent = _epl_weights(float(row.get("elo_diff", 0)))
        results.append(_blend_result(full_p[i], recent_p[i], w_full, w_recent))
        experts.append(FULL_EXPERT if w_full >= w_recent else RECENT_EXPERT)
    return results, experts


def _predict_wc_result(
    df: pd.DataFrame, league, stages: list
) -> tuple[list[dict], list[str]]:
    has_group = result_model.model_exists(league.key, GROUP_EXPERT)
    has_knockout = result_model.model_exists(league.key, KNOCKOUT_EXPERT)

    results, experts = [], []
    for i in range(len(df)):
        row_df = df.iloc[[i]]
        stage = stages[i] if i < len(stages) else None
        if _is_knockout(stage):
            if has_knockout:
                p = result_model.predict_proba(row_df, league, expert=KNOCKOUT_EXPERT)[0]
                exp = KNOCKOUT_EXPERT
            else:
                p = result_model.predict_proba(row_df, league)[0]
                exp = "combined"
        else:
            if has_group:
                p = result_model.predict_proba(row_df, league, expert=GROUP_EXPERT)[0]
                exp = GROUP_EXPERT
            else:
                p = result_model.predict_proba(row_df, league)[0]
                exp = "combined"
        results.append(p)
        experts.append(exp)
    return results, experts


def predict_scoreline(
    df: pd.DataFrame, league, stages: list[str | None] | None = None
) -> tuple[list[dict], list[str]]:
    """Returns (scoreline_probs_list, expert_names_list)."""
    n = len(df)
    stages = list(stages) if stages else [None] * n

    if league.key == "WORLD_CUP":
        return _predict_wc_scoreline(df, league, stages)
    return _predict_epl_scoreline(df, league)


def _predict_epl_scoreline(df: pd.DataFrame, league) -> tuple[list[dict], list[str]]:
    has_full = scoreline_model.model_exists(league.key, FULL_EXPERT)
    has_recent = scoreline_model.model_exists(league.key, RECENT_EXPERT)

    full_p = scoreline_model.predict_scoreline(df, league, expert=FULL_EXPERT) if has_full \
        else scoreline_model.predict_scoreline(df, league)
    recent_p = scoreline_model.predict_scoreline(df, league, expert=RECENT_EXPERT) if has_recent \
        else full_p

    results, experts = [], []
    for i, (_, row) in enumerate(df.iterrows()):
        w_full, w_recent = _epl_weights(float(row.get("elo_diff", 0)))
        results.append(_blend_scoreline(full_p[i], recent_p[i], w_full, w_recent))
        experts.append(FULL_EXPERT if w_full >= w_recent else RECENT_EXPERT)
    return results, experts


def _predict_wc_scoreline(
    df: pd.DataFrame, league, stages: list
) -> tuple[list[dict], list[str]]:
    has_group = scoreline_model.model_exists(league.key, GROUP_EXPERT)
    has_knockout = scoreline_model.model_exists(league.key, KNOCKOUT_EXPERT)

    results, experts = [], []
    for i in range(len(df)):
        row_df = df.iloc[[i]]
        stage = stages[i] if i < len(stages) else None
        if _is_knockout(stage):
            if has_knockout:
                p = scoreline_model.predict_scoreline(row_df, league, expert=KNOCKOUT_EXPERT)[0]
                exp = KNOCKOUT_EXPERT
            else:
                p = scoreline_model.predict_scoreline(row_df, league)[0]
                exp = "combined"
        else:
            if has_group:
                p = scoreline_model.predict_scoreline(row_df, league, expert=GROUP_EXPERT)[0]
                exp = GROUP_EXPERT
            else:
                p = scoreline_model.predict_scoreline(row_df, league)[0]
                exp = "combined"
        results.append(p)
        experts.append(exp)
    return results, experts


def predict_over_under(
    df: pd.DataFrame, league, stages: list[str | None] | None = None
) -> list[dict]:
    scorelines, _ = predict_scoreline(df, league, stages)
    return [
        {
            "over": round(sum(p for k, p in s.items()
                              if int(k.split("-")[0]) + int(k.split("-")[1]) > 2), 4),
            "under": round(sum(p for k, p in s.items()
                               if int(k.split("-")[0]) + int(k.split("-")[1]) <= 2), 4),
        }
        for s in scorelines
    ]


def predict_btts(
    df: pd.DataFrame, league, stages: list[str | None] | None = None
) -> list[dict]:
    scorelines, _ = predict_scoreline(df, league, stages)
    return [
        {
            "yes": round(sum(p for k, p in s.items()
                             if int(k.split("-")[0]) > 0 and int(k.split("-")[1]) > 0), 4),
            "no": round(sum(p for k, p in s.items()
                            if not (int(k.split("-")[0]) > 0 and int(k.split("-")[1]) > 0)), 4),
        }
        for s in scorelines
    ]
