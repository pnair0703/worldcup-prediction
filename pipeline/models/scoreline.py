"""
Poisson scoreline model.

Trains two PoissonRegressors (home goals, away goals) on the shared feature
matrix. The full scoreline distribution P(H=h, A=a) is the product of the two
independent Poisson PMFs, which also gives O/U 2.5 and BTTS for free.
"""
import os

import joblib
import pandas as pd
from scipy.stats import poisson
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MODEL_VERSION = "v1"
MAX_GOALS = 6  # P(H=h, A=a) for h,a in 0..MAX_GOALS


def _model_path(league_key: str) -> str:
    os.makedirs(MODEL_DIR, exist_ok=True)
    return os.path.join(MODEL_DIR, f"scoreline_{league_key}_{MODEL_VERSION}.joblib")


def train(df: pd.DataFrame, league) -> None:
    df = df.dropna(subset=["home_goals", "away_goals"] + league.feature_columns).copy()
    if len(df) < 30:
        raise ValueError(f"Too few training samples ({len(df)}) for {league.key}")

    X = df[league.feature_columns].astype(float).values
    y_h = df["home_goals"].astype(float).values
    y_a = df["away_goals"].astype(float).values

    reg_h = Pipeline([("scaler", StandardScaler()),
                      ("poisson", PoissonRegressor(alpha=1.0, max_iter=1000))])
    reg_a = Pipeline([("scaler", StandardScaler()),
                      ("poisson", PoissonRegressor(alpha=1.0, max_iter=1000))])
    reg_h.fit(X, y_h)
    reg_a.fit(X, y_a)
    joblib.dump({"home": reg_h, "away": reg_a}, _model_path(league.key))
    print(f"[scoreline] trained {len(df)} rows → {_model_path(league.key)}")


def _dist(lh: float, la: float) -> dict:
    """Scoreline distribution for h, a in 0..MAX_GOALS, normalised."""
    dist = {}
    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            dist[f"{h}-{a}"] = float(poisson.pmf(h, max(lh, 0.01)) *
                                     poisson.pmf(a, max(la, 0.01)))
    total = sum(dist.values())
    return {k: round(v / total, 5) for k, v in dist.items()}


def _load(league_key: str):
    return joblib.load(_model_path(league_key))


def predict_scoreline(df: pd.DataFrame, league) -> list[dict]:
    saved = _load(league.key)
    X = df[league.feature_columns].astype(float).values
    lh = saved["home"].predict(X)
    la = saved["away"].predict(X)
    return [_dist(float(h), float(a)) for h, a in zip(lh, la)]


def predict_over_under(df: pd.DataFrame, league) -> list[dict]:
    results = []
    for dist in predict_scoreline(df, league):
        over = sum(p for k, p in dist.items()
                   if int(k.split("-")[0]) + int(k.split("-")[1]) > 2)
        results.append({"over": round(over, 4), "under": round(1.0 - over, 4)})
    return results


def predict_btts(df: pd.DataFrame, league) -> list[dict]:
    results = []
    for dist in predict_scoreline(df, league):
        yes = sum(p for k, p in dist.items()
                  if int(k.split("-")[0]) > 0 and int(k.split("-")[1]) > 0)
        results.append({"yes": round(yes, 4), "no": round(1.0 - yes, 4)})
    return results


def model_exists(league_key: str) -> bool:
    return os.path.exists(_model_path(league_key))
