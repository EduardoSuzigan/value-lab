"""Reader que materializa Match/Odds persistidos no DataFrame que o domínio/backtest
consomem (decisão (c): o backtest passa a ler do banco via este reader, sem SQL no
walk-forward puro).

Schema de saída (= backtest._REQUIRED + league/season):
    date, league, season, home, away, home_goals, away_goals,
    o_home, o_draw, o_away, c_home, c_draw, c_away
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.etl.persist import upsert_matches
from app.services.backtest import _REQUIRED
from app.services.dataset import load_matches_df


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": datetime(2024, 5, 2),
                "league": "E0",
                "season": "2324",
                "home": "Liverpool",
                "away": "Everton",
                "home_goals": 0,
                "away_goals": 0,
                "o_home": 1.50,
                "o_draw": 4.0,
                "o_away": 6.0,
                "c_home": 1.45,
                "c_draw": 4.1,
                "c_away": 6.5,
            },
            {
                "date": datetime(2024, 5, 1),
                "league": "E0",
                "season": "2324",
                "home": "Arsenal",
                "away": "Chelsea",
                "home_goals": 2,
                "away_goals": 1,
                "o_home": 1.95,
                "o_draw": 3.6,
                "o_away": 4.2,
                "c_home": 1.80,
                "c_draw": 3.7,
                "c_away": 4.5,
            },
        ]
    )


def test_load_returns_backtest_schema_sorted_by_date(session):
    upsert_matches(session, _frame())
    df = load_matches_df(session, "E0", "2324")

    assert set(_REQUIRED).issubset(df.columns)
    assert list(df["date"]) == [datetime(2024, 5, 1), datetime(2024, 5, 2)]
    arsenal = df.iloc[0]
    assert arsenal["home"] == "Arsenal" and arsenal["away"] == "Chelsea"
    assert arsenal["home_goals"] == 2 and arsenal["away_goals"] == 1
    assert arsenal["o_home"] == 1.95 and arsenal["c_away"] == 4.5


def test_load_feeds_walk_forward(session):
    """O frame do reader é aceito pelo backtest sem ajuste (contrato de schema)."""
    from app.services import backtest as bt

    upsert_matches(session, _frame())
    df = load_matches_df(session, "E0", "2324")
    bt._validate(df)  # não levanta → schema compatível


def test_load_excludes_future_matches(session):
    """Jogos sem placar (futuros) não entram no dataset de modelagem."""
    df = _frame()
    df.loc[df["home"] == "Arsenal", ["home_goals", "away_goals"]] = None
    # placar None: simula jogo futuro persistido em Match
    from app.models import Match, Team

    upsert_matches(session, df)
    # força o Arsenal a futuro no banco (upsert do football-data já dropa sem placar,
    # mas Match permite None; garantimos o filtro do reader)
    ars = (
        session.query(Match)
        .join(Team, Match.home_team_id == Team.id)
        .filter(Team.name == "Arsenal")
        .one()
    )
    ars.home_goals = None
    ars.away_goals = None
    session.commit()

    out = load_matches_df(session, "E0", "2324")
    assert list(out["home"]) == ["Liverpool"]
