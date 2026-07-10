"""
Ingest fixtures + results from football-data.org (free tier).

Covers BOTH competitions through one client:
  - EPL        -> competition code 'PL'
  - World Cup  -> competition code 'WC'

Free tier needs an API key (register at football-data.org, ~2 min).
Set FOOTBALL_DATA_API_KEY in your .env.

Docs: https://www.football-data.org/documentation/quickstart
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import requests

BASE = "https://api.football-data.org/v4"

# Map our league keys -> football-data.org competition codes.
COMPETITION_CODE = {
    "EPL": "PL",
    "WORLD_CUP": "WC",
}


def _headers() -> dict:
    key = os.environ.get("FOOTBALL_DATA_API_KEY")
    if not key:
        raise RuntimeError(
            "FOOTBALL_DATA_API_KEY is not set. Register a free key at "
            "football-data.org and add it to your .env."
        )
    return {"X-Auth-Token": key}


def _parse_match(m: dict, league: str) -> dict:
    """Normalize a football-data.org match into our fixture dict."""
    score = m.get("score", {}).get("fullTime", {})
    home_goals = score.get("home")
    away_goals = score.get("away")
    status = "FINISHED" if m.get("status") == "FINISHED" else "SCHEDULED"

    return {
        "league": league,
        "source_match_id": str(m["id"]),
        "season": str(m.get("season", {}).get("startDate", "")[:4] or "2026"),
        "kickoff_utc": m["utcDate"],
        "home_team": m["homeTeam"]["name"],
        "away_team": m["awayTeam"]["name"],
        "stage": m.get("stage", "LEAGUE"),
        "home_goals": home_goals,
        "away_goals": away_goals,
        "status": status,
    }


def fetch_fixtures(league: str, date_from: str | None = None,
                   date_to: str | None = None,
                   season: str | None = None) -> list[dict]:
    """
    Return normalized fixtures for a league. Optional ISO date window
    (YYYY-MM-DD) or season year (e.g. "2023" for 2023/24).
    Without any filter, returns the competition's current matches.
    Fixtures with undetermined teams (future knockout slots) are excluded.
    """
    code = COMPETITION_CODE[league]
    url = f"{BASE}/competitions/{code}/matches"
    params = {}
    if date_from:
        params["dateFrom"] = date_from
    if date_to:
        params["dateTo"] = date_to
    if season:
        params["season"] = season

    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    if resp.status_code == 429:
        # free tier is rate limited; back off once and retry
        time.sleep(6)
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()

    matches = resp.json().get("matches", [])
    parsed = [_parse_match(m, league) for m in matches]
    # drop fixtures where teams aren't determined yet (future knockout slots)
    return [f for f in parsed if f["home_team"] and f["away_team"]]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
