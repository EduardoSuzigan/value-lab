"""Persistência do ETL: DataFrame normalizado → Match/Odds (upsert idempotente).

Invariante (predictions-append-only.md): o ETL escreve SÓ Match/Odds; nunca
Prediction nem ModelRun. Chave natural do match: liga+season+date+home+away.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.etl.persist import upsert_matches
from app.models import League, Match, Odds, Prediction, Team


def _frame(close_home: float = 1.80) -> pd.DataFrame:
    """Dois jogos da E0, schema idêntico ao football_data.load()."""
    return pd.DataFrame(
        [
            {
                "date": datetime(2024, 5, 1),
                "league": "E0",
                "season": "2324",
                "home": "Arsenal",
                "away": "Chelsea",
                "home_goals": 2,
                "away_goals": 1,
                "o_home": 1.95, "o_draw": 3.6, "o_away": 4.2,
                "c_home": close_home, "c_draw": 3.7, "c_away": 4.5,
            },
            {
                "date": datetime(2024, 5, 2),
                "league": "E0",
                "season": "2324",
                "home": "Liverpool",
                "away": "Everton",
                "home_goals": 0,
                "away_goals": 0,
                "o_home": 1.50, "o_draw": 4.0, "o_away": 6.0,
                "c_home": 1.45, "c_draw": 4.1, "c_away": 6.5,
            },
        ]
    )


def test_upsert_creates_league_teams_matches_odds(session):
    upsert_matches(session, _frame())

    league = session.query(League).one()
    assert league.code == "E0"
    assert league.name == "Premier League"  # metadados vêm do registry
    assert league.country == "England"
    assert {t.name for t in session.query(Team)} == {
        "Arsenal", "Chelsea", "Liverpool", "Everton"
    }
    assert session.query(Match).count() == 2
    # 2 jogos × mercado 1X2 (3 seleções) = 6 linhas de Odds
    assert session.query(Odds).count() == 6
    ars = session.query(Match).filter_by(season="2324").first()
    assert ars.home_team.name == "Arsenal"
    home_odd = (
        session.query(Odds)
        .filter_by(match_id=ars.id, market="1X2", selection="home")
        .one()
    )
    assert home_odd.open == 1.95 and home_odd.close == 1.80


def test_upsert_is_idempotent(session):
    upsert_matches(session, _frame())
    upsert_matches(session, _frame())  # rodar de novo não duplica

    assert session.query(League).count() == 1
    assert session.query(Team).count() == 4
    assert session.query(Match).count() == 2
    assert session.query(Odds).count() == 6


def test_upsert_updates_existing_odds_in_place(session):
    upsert_matches(session, _frame(close_home=1.80))
    upsert_matches(session, _frame(close_home=1.70))  # odd de fechamento mudou

    assert session.query(Odds).count() == 6  # sem nova linha
    arsenal = (
        session.query(Team).filter_by(name="Arsenal").one()
    )
    odd = (
        session.query(Odds)
        .join(Match, Odds.match_id == Match.id)
        .filter(Match.home_team_id == arsenal.id, Odds.selection == "home")
        .one()
    )
    assert odd.close == 1.70  # atualizado in-place


def test_upsert_never_writes_predictions(session):
    upsert_matches(session, _frame())
    assert session.query(Prediction).count() == 0


def test_upsert_reschedule_updates_date_in_place(session):
    """Jogo remarcado (mesma liga/season/home/away, nova data) atualiza a data
    in-place — não cria um Match duplicado nem fragmenta as Odds."""
    upsert_matches(session, _frame())
    rescheduled = _frame()
    rescheduled.loc[
        (rescheduled["home"] == "Arsenal"), "date"
    ] = datetime(2024, 5, 8)
    upsert_matches(session, rescheduled)

    assert session.query(Match).count() == 2  # não duplicou
    assert session.query(Odds).count() == 6
    ars = (
        session.query(Match)
        .join(Team, Match.home_team_id == Team.id)
        .filter(Team.name == "Arsenal")
        .one()
    )
    assert ars.date == datetime(2024, 5, 8)
