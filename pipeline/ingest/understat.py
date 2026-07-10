"""
Ingest shot-level xG data from Understat (EPL only, free, no key).

Understat is the backbone of the EPL model's quality signal. It publishes xG,
xA, xGChain and xGBuildup back to 2014/15 for the top-5 European leagues. We
use the `understat` async library, which wraps their public endpoints.

International / World Cup matches are NOT covered by Understat, which is exactly
why the WORLD_CUP league declares has_xg=False and falls back to Elo + form.

Output: a per-team, per-match xG table the feature builder turns into rolling
averages.
"""

import asyncio

import aiohttp

try:
    from understat import Understat
except ImportError:  # keep import-safe even if the optional dep is missing
    Understat = None


async def _fetch_epl_results(season: int) -> list[dict]:
    async with aiohttp.ClientSession() as session:
        us = Understat(session)
        # results = finished matches with team-level xG attached
        return await us.get_league_results("epl", season)


def fetch_epl_xg(season: int) -> list[dict]:
    """
    Return a flat list of {match, team, is_home, goals, xg, opp_xg} rows for a
    season. Two rows per match (home + away) so the feature builder can compute
    rolling per-team xG for/against.
    """
    if Understat is None:
        raise RuntimeError(
            "The 'understat' package is not installed. Run "
            "`pip install understat aiohttp`."
        )

    raw = asyncio.run(_fetch_epl_results(season))
    rows: list[dict] = []
    for m in raw:
        h, a = m["h"]["title"], m["a"]["title"]
        h_xg, a_xg = float(m["xG"]["h"]), float(m["xG"]["a"])
        h_g, a_g = int(m["goals"]["h"]), int(m["goals"]["a"])
        date = m["datetime"]
        rows.append({"match": m["id"], "date": date, "team": h, "is_home": 1,
                     "goals": h_g, "xg": h_xg, "opp_xg": a_xg})
        rows.append({"match": m["id"], "date": date, "team": a, "is_home": 0,
                     "goals": a_g, "xg": a_xg, "opp_xg": h_xg})
    return rows
