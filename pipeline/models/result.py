"""
Match result model: home win / draw / away win.

XGBoost multiclass classifier trained on League.feature_columns.
Persisted to pipeline/data/ keyed by league + model version.
"""
from __future__ import annotations

import os

import joblib
import pandas as pd
from xgboost import XGBClassifier

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MODEL_VERSION = "v1"

LABEL_TO_IDX = {"home": 0, "draw": 1, "away": 2}
IDX_TO_LABEL = {v: k for k, v in LABEL_TO_IDX.items()}


def _model_path(league_key: str) -> str:
    os.makedirs(MODEL_DIR, exist_ok=True)
    return os.path.join(MODEL_DIR, f"result_{league_key}_{MODEL_VERSION}.joblib")


def _make_label(row) -> str | None:
    if pd.isna(row["home_goals"]) or pd.isna(row["away_goals"]):
        return None
    hg, ag = int(row["home_goals"]), int(row["away_goals"])
    if hg > ag:
        return "home"
    if ag > hg:
        return "away"
    return "draw"


def train(df: pd.DataFrame, league) -> None:
    df = df.copy()
    df["_label"] = df.apply(_make_label, axis=1)
    df = df.dropna(subset=["_label"] + league.feature_columns)
    if len(df) < 30:
        raise ValueError(f"Too few training samples ({len(df)}) for {league.key}")

    X = df[league.feature_columns].astype(float).values
    y = df["_label"].map(LABEL_TO_IDX).values

    model = XGBClassifier(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.04,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="multi:softprob",
        num_class=3,
        eval_metric="mlogloss",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X, y)
    joblib.dump(model, _model_path(league.key))
    print(f"[result] trained {len(df)} rows → {_model_path(league.key)}")


def predict_proba(df: pd.DataFrame, league) -> list[dict]:
    """Return [{"home": p, "draw": p, "away": p}, ...] for each row."""
    model = joblib.load(_model_path(league.key))
    X = df[league.feature_columns].astype(float).values
    probs = model.predict_proba(X)  # shape (n, 3); cols = [home, draw, away]
    return [
        {IDX_TO_LABEL[i]: round(float(p), 4) for i, p in enumerate(row)}
        for row in probs
    ]


def model_exists(league_key: str) -> bool:
    return os.path.exists(_model_path(league_key))
