"""train_league: fit Dixon-Coles por (liga, temporada) → ModelRun + Predictions.

Invariantes: ModelRun é por liga (per-league-fit.md); Prediction por
(run, match, market, selection), todos os mercados (1X2/OU25/BTTS) de uma vez;
append-only (re-treinar cria um NOVO run, nunca sobrescreve); train NÃO escreve
Match/Odds (só o ETL).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from app.etl.persist import upsert_matches
from app.models import Match, ModelRun, Odds, Prediction
from app.services.train import train_league

_TEAMS = ("A", "B", "C", "D")
_HG = [2, 1, 0, 3, 1, 2, 1, 0, 2, 1, 3, 0]
_AG = [1, 1, 2, 0, 1, 0, 2, 1, 1, 2, 0, 1]


def _league_frame() -> pd.DataFrame:
    pairs = [(h, a) for h in _TEAMS for a in _TEAMS if h != a]  # 12 jogos
    base = datetime(2024, 1, 1)
    rows = []
    for i, (h, a) in enumerate(pairs):
        rows.append(
            {
                "date": base + timedelta(days=i),
                "league": "E0",
                "season": "2324",
                "home": h,
                "away": a,
                "home_goals": _HG[i],
                "away_goals": _AG[i],
                "o_home": 2.0, "o_draw": 3.3, "o_away": 3.8,
                "c_home": 1.95, "c_draw": 3.4, "c_away": 4.0,
            }
        )
    return pd.DataFrame(rows)


def _seed(session) -> None:
    upsert_matches(session, _league_frame())


def test_train_creates_run_and_all_market_predictions(session):
    _seed(session)
    run = train_league(session, "E0", "2324")

    assert isinstance(run, ModelRun)
    assert run.league.code == "E0" and run.season == "2324"
    n_matches = session.query(Match).count()
    # 7 linhas por jogo: 1X2(3) + OU25(2) + BTTS(2)
    assert session.query(Prediction).count() == n_matches * 7
    assert all(p.run_id == run.id for p in session.query(Prediction))


def test_predictions_are_coherent_probabilities(session):
    _seed(session)
    run = train_league(session, "E0", "2324")
    match = session.query(Match).first()

    def probs(market):
        return {
            p.selection: p.prob
            for p in session.query(Prediction).filter_by(
                run_id=run.id, match_id=match.id, market=market
            )
        }

    x12 = probs("1X2")
    assert abs(sum(x12.values()) - 1.0) < 1e-6
    assert set(x12) == {"home", "draw", "away"}
    ou = probs("OU25")
    assert abs(ou["over"] + ou["under"] - 1.0) < 1e-6
    btts = probs("BTTS")
    assert abs(btts["yes"] + btts["no"] - 1.0) < 1e-6


def test_retrain_appends_new_run_without_overwriting(session):
    _seed(session)
    run1 = train_league(session, "E0", "2324")
    n1 = session.query(Prediction).filter_by(run_id=run1.id).count()
    run2 = train_league(session, "E0", "2324")

    assert run2.id != run1.id  # novo run, não sobrescreve
    assert session.query(ModelRun).count() == 2
    # predições do run1 intactas + novas do run2
    assert session.query(Prediction).filter_by(run_id=run1.id).count() == n1
    assert session.query(Prediction).filter_by(run_id=run2.id).count() == n1


def test_train_does_not_touch_match_or_odds(session):
    _seed(session)
    n_match = session.query(Match).count()
    n_odds = session.query(Odds).count()
    train_league(session, "E0", "2324")
    assert session.query(Match).count() == n_match
    assert session.query(Odds).count() == n_odds
