"""Materializa Match/Odds persistidos no DataFrame que o domínio/backtest consomem.

Decisão (c): o backtest passa a ler do banco através deste reader (camada de
services orquestra persistência → DataFrame), mantendo o `walk_forward_clv` puro,
sem SQL no laço de refit. Saída idêntica ao `football_data.load()`:

    date, league, season, home, away, home_goals, away_goals,
    o_home, o_draw, o_away, c_home, c_draw, c_away

Só jogos DISPUTADOS (placar presente) entram — jogos futuros (placar None) não
servem para treinar/avaliar.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.models import League, Match, Odds, Team

_SELECTIONS = ("home", "draw", "away")
_MARKET_1X2 = "1X2"
_COLUMNS = (
    "date",
    "league",
    "season",
    "home",
    "away",
    "home_goals",
    "away_goals",
    "o_home",
    "o_draw",
    "o_away",
    "c_home",
    "c_draw",
    "c_away",
)


def load_matches_df(
    session: Session, league: str, season: str | None = None
) -> pd.DataFrame:
    """Frame normalizado de uma liga (e temporada opcional), ordenado por data."""
    home_t = aliased(Team)
    away_t = aliased(Team)
    q = (
        select(
            Match.id.label("match_id"),
            Match.date,
            League.code.label("league"),
            Match.season,
            home_t.name.label("home"),
            away_t.name.label("away"),
            Match.home_goals,
            Match.away_goals,
        )
        .join(League, Match.league_id == League.id)
        .join(home_t, Match.home_team_id == home_t.id)
        .join(away_t, Match.away_team_id == away_t.id)
        .where(
            League.code == league,
            Match.home_goals.is_not(None),
            Match.away_goals.is_not(None),
        )
    )
    if season is not None:
        q = q.where(Match.season == season)

    matches = pd.DataFrame(
        session.execute(q).mappings().all(),
        columns=[
            "match_id",
            "date",
            "league",
            "season",
            "home",
            "away",
            "home_goals",
            "away_goals",
        ],
    )
    if matches.empty:
        return pd.DataFrame(columns=list(_COLUMNS))

    odds = _load_odds(session, matches["match_id"].tolist())
    for kind, prefix in (("open", "o"), ("close", "c")):
        wide = odds.pivot(index="match_id", columns="selection", values=kind)
        wide = wide.reindex(columns=_SELECTIONS)
        for sel in _SELECTIONS:
            matches[f"{prefix}_{sel}"] = matches["match_id"].map(wide[sel])

    return (
        matches.drop(columns=["match_id"])
        .sort_values("date", kind="stable")
        .reset_index(drop=True)
    )


def _load_odds(session: Session, match_ids: list[int]) -> pd.DataFrame:
    q = select(Odds.match_id, Odds.selection, Odds.open, Odds.close).where(
        Odds.match_id.in_(match_ids), Odds.market == _MARKET_1X2
    )
    return pd.DataFrame(
        session.execute(q).mappings().all(),
        columns=["match_id", "selection", "open", "close"],
    )
