"""
Feature engineering shared by every competition.

Computes, for each fixture, the feature vector declared by its League:
  - Elo ratings (updated match-by-match over history)
  - rolling form: points-per-game, goals for/against (last N)
  - rolling xG for/against  (EPL only, when has_xg)
  - rest-days difference, neutral-venue flag

The League object decides which columns survive; the model trains on exactly
League.feature_columns, so EPL gets xG columns and the World Cup doesn't.
"""

from __future__ import annotations

from collections import defaultdict, deque

import pandas as pd

from ..league import League

ROLL = 5            # rolling window for form
ELO_K = 24          # Elo update sensitivity
ELO_HOME_ADV = 60   # home-advantage bump (ignored at neutral venues)
ELO_BASE = 1500


class EloBook:
    """Tracks running Elo per team across the season's chronological matches."""

    def __init__(self):
        self.r = defaultdict(lambda: ELO_BASE)

    def expected(self, home, away, neutral=False):
        adv = 0 if neutral else ELO_HOME_ADV
        diff = (self.r[home] + adv) - self.r[away]
        return 1.0 / (1.0 + 10 ** (-diff / 400))

    def update(self, home, away, home_goals, away_goals, neutral=False):
        exp_home = self.expected(home, away, neutral)
        if home_goals > away_goals:
            s_home = 1.0
        elif home_goals < away_goals:
            s_home = 0.0
        else:
            s_home = 0.5
        # margin-of-victory multiplier keeps blowouts from overweighting
        mov = 1 + 0.3 * abs(home_goals - away_goals)
        delta = ELO_K * mov * (s_home - exp_home)
        self.r[home] += delta
        self.r[away] -= delta


def _rolling(history: deque) -> dict:
    """Aggregate a team's recent matches into form features."""
    if not history:
        return {"form_pts": 1.0, "gf_avg": 1.2, "ga_avg": 1.2,
                "xg_for_avg": 1.2, "xg_against_avg": 1.2}
    pts = sum(h["pts"] for h in history) / len(history)
    gf = sum(h["gf"] for h in history) / len(history)
    ga = sum(h["ga"] for h in history) / len(history)
    xgf = sum(h.get("xgf", h["gf"]) for h in history) / len(history)
    xga = sum(h.get("xga", h["ga"]) for h in history) / len(history)
    return {"form_pts": pts, "gf_avg": gf, "ga_avg": ga,
            "xg_for_avg": xgf, "xg_against_avg": xga}


def build_features(matches: pd.DataFrame, league: League,
                   xg_lookup: dict | None = None) -> pd.DataFrame:
    """
    matches: chronological df with columns
        [date, home_team, away_team, home_goals, away_goals, neutral]
        (goals may be NaN for upcoming fixtures we want to predict)
    xg_lookup: optional {(date, team): {"xgf":..,"xga":..}} for EPL
    Returns a df with one row per match and League.feature_columns populated.
    """
    matches = matches.sort_values("date").reset_index(drop=True)
    elo = EloBook()
    recent: dict[str, deque] = defaultdict(lambda: deque(maxlen=ROLL))
    last_played: dict[str, pd.Timestamp] = {}
    rows = []

    for _, m in matches.iterrows():
        home, away = m["home_team"], m["away_team"]
        neutral = bool(m.get("neutral", False))
        date = pd.to_datetime(m["date"])

        hf = _rolling(recent[home])
        af = _rolling(recent[away])

        rest_home = (date - last_played[home]).days if home in last_played else 7
        rest_away = (date - last_played[away]).days if away in last_played else 7

        feat = {
            "elo_diff": elo.r[home] - elo.r[away] + (0 if neutral else ELO_HOME_ADV),
            "home_form_pts": hf["form_pts"],
            "away_form_pts": af["form_pts"],
            "home_gf_avg": hf["gf_avg"],
            "away_gf_avg": af["gf_avg"],
            "home_ga_avg": hf["ga_avg"],
            "away_ga_avg": af["ga_avg"],
            "rest_days_diff": rest_home - rest_away,
            "is_neutral_venue": int(neutral),
        }
        if league.has_xg:
            feat.update({
                "home_xg_for_avg": hf["xg_for_avg"],
                "away_xg_for_avg": af["xg_for_avg"],
                "home_xg_against_avg": hf["xg_against_avg"],
                "away_xg_against_avg": af["xg_against_avg"],
                "home_xg_diff_avg": hf["xg_for_avg"] - hf["xg_against_avg"],
                "away_xg_diff_avg": af["xg_for_avg"] - af["xg_against_avg"],
            })

        # carry through identifiers + label material
        feat["date"] = date
        feat["home_team"] = home
        feat["away_team"] = away
        feat["home_goals"] = m.get("home_goals")
        feat["away_goals"] = m.get("away_goals")
        rows.append(feat)

        # update state ONLY for finished matches (don't leak future info)
        if pd.notna(m.get("home_goals")) and pd.notna(m.get("away_goals")):
            hg, ag = int(m["home_goals"]), int(m["away_goals"])
            elo.update(home, away, hg, ag, neutral)
            h_pts = 3 if hg > ag else (1 if hg == ag else 0)
            a_pts = 3 if ag > hg else (1 if hg == ag else 0)
            h_extra, a_extra = {}, {}
            if xg_lookup:
                h_extra = xg_lookup.get((str(date.date()), home), {})
                a_extra = xg_lookup.get((str(date.date()), away), {})
            recent[home].append({"pts": h_pts, "gf": hg, "ga": ag, **h_extra})
            recent[away].append({"pts": a_pts, "gf": ag, "ga": hg, **a_extra})
            last_played[home] = date
            last_played[away] = date

    return pd.DataFrame(rows)
