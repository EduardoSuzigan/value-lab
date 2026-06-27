"""Persistência do ETL: DataFrame normalizado → Match/Odds (upsert idempotente).

Recebe o frame do `football_data.load()` (uma liga/temporada) e grava em
Match/Odds com chave natural liga+season+date+home+away. Idempotente: rodar de
novo atualiza placar/odds in-place, sem duplicar.

Invariante (ver .claude/rules/predictions-append-only.md): o ETL escreve SOMENTE
em Match/Odds — NUNCA em Prediction/ModelRun. Os metadados de liga (name/country)
vêm do registro de fontes, não do CSV.

Upsert via SELECT-then-INSERT/UPDATE (portável SQLite/Postgres), não ON CONFLICT
de um dialeto específico — assim o teste em SQLite exercita o mesmo caminho da
produção em Neon.
"""

from __future__ import annotations

import math

import pandas as pd
from sqlalchemy.orm import Session

from app.etl.sources import registry
from app.models import League, Match, Odds, Team

_SELECTIONS = ("home", "draw", "away")
_MARKET_1X2 = "1X2"


def upsert_matches(session: Session, df: pd.DataFrame) -> dict[str, int]:
    """Grava o frame normalizado em Match/Odds. Retorna contagem de linhas tocadas."""
    n_matches = 0
    n_odds = 0
    for row in df.itertuples(index=False):
        league = _get_or_create_league(session, row.league)
        home = _get_or_create_team(session, league, row.home)
        away = _get_or_create_team(session, league, row.away)
        match = _upsert_match(session, league, home, away, row)
        n_matches += 1
        n_odds += _upsert_1x2_odds(session, match, row)
    session.commit()
    return {"matches": n_matches, "odds": n_odds}


def _get_or_create_league(session: Session, code: str) -> League:
    league = session.query(League).filter_by(code=code).one_or_none()
    if league is None:
        src = registry.get_source(code)  # metadados canônicos da liga
        league = League(
            code=code,
            name=src.name,
            country=src.country,
            experimental=src.experimental,
        )
        session.add(league)
        session.flush()
    return league


def _get_or_create_team(session: Session, league: League, name: str) -> Team:
    team = (
        session.query(Team)
        .filter_by(league_id=league.id, name=name)
        .one_or_none()
    )
    if team is None:
        team = Team(league_id=league.id, name=name)
        session.add(team)
        session.flush()
    return team


def _upsert_match(
    session: Session, league: League, home: Team, away: Team, row
) -> Match:
    date = pd.Timestamp(row.date).to_pydatetime()
    match = (
        session.query(Match)
        .filter_by(
            league_id=league.id,
            season=row.season,
            home_team_id=home.id,
            away_team_id=away.id,
        )
        .one_or_none()
    )
    home_goals = _int_or_none(row.home_goals)
    away_goals = _int_or_none(row.away_goals)
    if match is None:
        match = Match(
            league_id=league.id,
            season=row.season,
            date=date,
            home_team_id=home.id,
            away_team_id=away.id,
            home_goals=home_goals,
            away_goals=away_goals,
        )
        session.add(match)
        session.flush()
    else:  # remarcação/placar atualizam in-place (date é atributo, não chave)
        match.date = date
        match.home_goals = home_goals
        match.away_goals = away_goals
    return match


def _upsert_1x2_odds(session: Session, match: Match, row) -> int:
    n = 0
    for sel in _SELECTIONS:
        open_v = _float_or_none(getattr(row, f"o_{sel}"))
        close_v = _float_or_none(getattr(row, f"c_{sel}"))
        odd = (
            session.query(Odds)
            .filter_by(match_id=match.id, market=_MARKET_1X2, selection=sel)
            .one_or_none()
        )
        if odd is None:
            session.add(
                Odds(
                    match_id=match.id,
                    market=_MARKET_1X2,
                    selection=sel,
                    open=open_v,
                    close=close_v,
                )
            )
        else:
            odd.open = open_v
            odd.close = close_v
        n += 1
    return n


def _float_or_none(v) -> float | None:
    if v is None:
        return None
    f = float(v)
    return None if math.isnan(f) else f


def _int_or_none(v) -> int | None:
    f = _float_or_none(v)
    return None if f is None else int(f)
