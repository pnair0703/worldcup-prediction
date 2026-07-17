"""
League abstraction.

The whole point of footy-oracle is that EPL and the World Cup run through ONE
engine. They differ only in (a) where their data comes from and (b) which
features are available. EPL has rich shot-level xG (via Understat); the World
Cup does not, because international xG basically doesn't exist in free sources.

Each League declares its feature set. The model layer reads `feature_columns`
and trains/predicts on exactly those columns, so adding a new competition is
just: write an ingester + declare a League here.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class League:
    key: str                      # 'EPL' | 'WORLD_CUP'
    display_name: str
    has_xg: bool                  # rich shot data available?
    feature_columns: list[str] = field(default_factory=list)


# Shared features every competition can compute from results alone.
_BASE_FEATURES = [
    "elo_diff",            # home Elo - away Elo
    "home_form_pts",       # points per game, last 5
    "away_form_pts",
    "home_gf_avg",         # goals for, rolling
    "away_gf_avg",
    "home_ga_avg",         # goals against, rolling
    "away_ga_avg",
    "rest_days_diff",      # home rest - away rest
    "is_neutral_venue",    # 1 for most WC games, 0 for league games
]

# xG-derived features, EPL only.
_XG_FEATURES = [
    "home_xg_for_avg",
    "away_xg_for_avg",
    "home_xg_against_avg",
    "away_xg_against_avg",
    "home_xg_diff_avg",    # xG for - xG against (underlying quality signal)
    "away_xg_diff_avg",
]


EPL = League(
    key="EPL",
    display_name="Premier League",
    has_xg=True,
    feature_columns=_BASE_FEATURES + _XG_FEATURES,
)

WORLD_CUP = League(
    key="WORLD_CUP",
    display_name="World Cup 2026",
    has_xg=False,
    feature_columns=_BASE_FEATURES,   # no xG: leans on Elo + form, the honest way
)

LEAGUES: dict[str, League] = {lg.key: lg for lg in (EPL, WORLD_CUP)}


def get_league(key: str) -> League:
    try:
        return LEAGUES[key]
    except KeyError:
        raise ValueError(f"Unknown league '{key}'. Known: {list(LEAGUES)}")
