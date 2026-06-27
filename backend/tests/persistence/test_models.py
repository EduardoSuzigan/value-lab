"""Schema de persistência (Fase 1): Team, League, Match, Odds, ModelRun, Prediction.

Invariantes (ver .claude/rules/predictions-append-only.md):
- Match.placar None = jogo futuro.
- ModelRun por liga; Prediction por (run, match, market, selection), append-only.
- Odds = fonte de verdade do CLV (abertura/fechamento por seleção).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import League, Match, ModelRun, Odds, Prediction, Team


def _league(session) -> League:
    league = League(code="E0", name="Premier League", country="England")
    session.add(league)
    session.commit()
    return league


def _match(session, league: League) -> Match:
    match = Match(
        league=league,
        season="2324",
        date=datetime(2024, 5, 1),
        home_team=Team(league=league, name="Arsenal"),
        away_team=Team(league=league, name="Chelsea"),
        home_goals=2,
        away_goals=1,
    )
    session.add(match)
    session.commit()
    return match


def test_full_graph_round_trip(session):
    """Liga → Times → Match (com Odds) e ModelRun → Prediction round-trip."""
    epl = League(code="E0", name="Premier League", country="England")
    home = Team(league=epl, name="Arsenal")
    away = Team(league=epl, name="Chelsea")
    match = Match(
        league=epl,
        season="2324",
        date=datetime(2024, 5, 1),
        home_team=home,
        away_team=away,
        home_goals=2,
        away_goals=1,
    )
    match.odds.append(
        Odds(market="1X2", selection="home", open=1.95, close=1.80)
    )
    run = ModelRun(league=epl, season="2324", xi=0.005)
    run.predictions.append(
        Prediction(match=match, market="1X2", selection="home", prob=0.55)
    )
    session.add_all([epl, match, run])
    session.commit()

    got = session.query(Match).one()
    assert got.home_team.name == "Arsenal"
    assert got.away_team.name == "Chelsea"
    assert got.league.code == "E0"
    assert got.odds[0].close == 1.80
    assert session.query(Prediction).one().prob == 0.55
    assert session.query(ModelRun).one().predictions[0].selection == "home"


def test_match_score_none_means_future(session):
    """Match sem placar (jogo futuro) é permitido."""
    epl = League(code="E0", name="Premier League", country="England")
    match = Match(
        league=epl,
        season="2324",
        date=datetime(2024, 5, 1),
        home_team=Team(league=epl, name="Arsenal"),
        away_team=Team(league=epl, name="Chelsea"),
        home_goals=None,
        away_goals=None,
    )
    session.add(match)
    session.commit()

    got = session.query(Match).one()
    assert got.home_goals is None and got.away_goals is None


def test_league_code_is_unique(session):
    session.add(League(code="E0", name="Premier League", country="England"))
    session.commit()
    session.add(League(code="E0", name="Duplicada", country="England"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_team_unique_per_league(session):
    league = _league(session)
    session.add_all([Team(league=league, name="Arsenal"),
                     Team(league=league, name="Arsenal")])
    with pytest.raises(IntegrityError):
        session.commit()


def test_match_natural_key_is_unique(session):
    """(liga, season, date, home, away) é a chave natural do upsert idempotente."""
    league = _league(session)
    match = _match(session, league)
    dup = Match(
        league=league,
        season=match.season,
        date=match.date,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        home_goals=0,
        away_goals=0,
    )
    session.add(dup)
    with pytest.raises(IntegrityError):
        session.commit()


def test_odds_unique_per_market_selection(session):
    league = _league(session)
    match = _match(session, league)
    session.add_all([
        Odds(match=match, market="1X2", selection="home", open=1.9, close=1.8),
        Odds(match=match, market="1X2", selection="home", open=2.0, close=1.7),
    ])
    with pytest.raises(IntegrityError):
        session.commit()


def test_prediction_unique_per_run_match_market_selection(session):
    league = _league(session)
    match = _match(session, league)
    run = ModelRun(league=league, season="2324", xi=0.005)
    session.add(run)
    session.commit()
    session.add_all([
        Prediction(run=run, match=match, market="1X2", selection="home", prob=0.5),
        Prediction(run=run, match=match, market="1X2", selection="home", prob=0.6),
    ])
    with pytest.raises(IntegrityError):
        session.commit()


def test_foreign_keys_are_enforced(session):
    """FK dangling deve falhar (em SQLite exige PRAGMA foreign_keys=ON)."""
    league = _league(session)
    match = _match(session, league)
    session.add(
        Prediction(run_id=999, match_id=match.id, market="1X2",
                   selection="home", prob=0.5)
    )
    with pytest.raises(IntegrityError):
        session.commit()
