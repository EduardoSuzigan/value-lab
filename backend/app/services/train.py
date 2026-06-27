"""Treino por (liga, temporada): fit Dixon-Coles → ModelRun + Predictions.

Camada de SERVICES: orquestra o domínio (dixon_coles) + persistência. Fit é POR
LIGA, nunca pooled (per-league-fit.md): cada chamada gera um ModelRun e suas
Predictions, append-only — re-treinar cria um run novo, nunca sobrescreve.

Grava todos os mercados de uma vez (decisão (b)): por (run, match, market,
selection). Lê Match/Odds do banco via `load_matches_df` (decisão (c)); NUNCA
escreve Match/Odds — isso é exclusivo do ETL.

Nota honesta: estas predições são in-sample (modelo atual sobre os jogos da
temporada), úteis p/ servir no dashboard. A avaliação honesta (CLV/calibração)
continua no walk-forward de `backtest.py`, sem look-ahead.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.domain import dixon_coles as dc
from app.models import League, Match, ModelRun, Prediction
from app.services.dataset import load_matches_df

_DEFAULT_XI = 0.005  # decaimento temporal (>0); calibração fina fica p/ a Fase 4
_MIN_MATCHES = 10

# (market, selection) → chave do dict retornado por DixonColesModel.predict().
# BTTS "no" é derivado (1 - btts), por isso não está aqui.
_DIRECT = (
    ("1X2", "home", "home_win"),
    ("1X2", "draw", "draw"),
    ("1X2", "away", "away_win"),
    ("OU25", "over", "over_2_5"),
    ("OU25", "under", "under_2_5"),
    ("BTTS", "yes", "btts"),
)


def train_league(
    session: Session,
    league_code: str,
    season: str,
    xi: float = _DEFAULT_XI,
    ref_date: datetime | None = None,
) -> ModelRun:
    """Treina uma liga/temporada e persiste um ModelRun + suas Predictions."""
    df = load_matches_df(session, league_code, season)
    if len(df) < _MIN_MATCHES:
        raise ValueError(
            f"poucos jogos p/ treinar {league_code} {season}: {len(df)} "
            f"(< {_MIN_MATCHES})"
        )
    model = dc.fit(df, xi=xi, ref_date=ref_date)

    league = session.query(League).filter_by(code=league_code).one()
    run = ModelRun(league_id=league.id, season=season, xi=xi)
    session.add(run)
    session.flush()  # garante run.id p/ as Predictions

    matches = (
        session.query(Match)
        .filter_by(league_id=league.id, season=season)
        .all()
    )
    for match in matches:
        home, away = match.home_team.name, match.away_team.name
        if home not in model.attack or away not in model.attack:
            continue  # time sem histórico no fit → sem predição
        pred = model.predict(home, away)
        for market, selection, prob in _prediction_rows(pred):
            session.add(
                Prediction(
                    run_id=run.id,
                    match_id=match.id,
                    market=market,
                    selection=selection,
                    prob=prob,
                )
            )
    session.commit()
    return run


def _prediction_rows(pred: dict[str, float]):
    for market, selection, key in _DIRECT:
        yield market, selection, pred[key]
    yield "BTTS", "no", 1.0 - pred["btts"]
