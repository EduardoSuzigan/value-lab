"""Backtest walk-forward de CLV + calibração para UMA liga.

Camada de SERVICES: orquestra o domínio (dixon_coles + eval) sobre um histórico
de partidas com odds de abertura e fechamento. NUNCA otimiza por ROID histórico —
o critério honesto é o CLV (odds de entrada vs. linha de FECHAMENTO) e a calibração.

Para multi-liga, o chamador itera por liga e roda este backtest por liga (fit por
liga, nunca pooled — ver .claude/rules/per-league-fit.md).

Schema esperado de `matches` (DataFrame), uma liga, ordenável por `date`:
    date, home, away, home_goals, away_goals,
    o_home, o_draw, o_away,   # odds decimais de ABERTURA (entrada)
    c_home, c_draw, c_away    # odds decimais de FECHAMENTO (benchmark do CLV)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.domain import dixon_coles as dc
from app.domain import eval as ev

_SELECTIONS = ("home", "draw", "away")
_PRED_KEY = {"home": "home_win", "draw": "draw", "away": "away_win"}
_REQUIRED = (
    "date",
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


@dataclass
class BetRecord:
    selection: str
    p_model: float
    entry_odd: float
    closing_odd: float
    ev: float
    beat_closing: bool


@dataclass
class BacktestResult:
    n_matches: int
    n_bets: int
    beat_closing_rate: float | None
    avg_ev: float | None
    brier: float
    log_loss: float
    calibration: tuple[list[float], list[float], list[int]]
    match_preds: list[dict] = field(default_factory=list)


def evaluate_value_bets(
    probs: dict[str, float],
    opening: dict[str, float],
    closing: dict[str, float],
    ev_threshold: float = 0.0,
) -> list[BetRecord]:
    """Para cada seleção 1X2, sinaliza value bet (EV na odd de ENTRADA > threshold).

    EV = p_model * odd_entrada - 1. `beat_closing` = odd de entrada > odd de
    fechamento (pegamos preço melhor que o close → CLV positivo).
    """
    bets: list[BetRecord] = []
    for sel in _SELECTIONS:
        p = probs[sel]
        entry = opening[sel]
        close = closing[sel]
        ev_val = p * entry - 1.0
        if ev_val > ev_threshold:
            bets.append(
                BetRecord(
                    selection=sel,
                    p_model=p,
                    entry_odd=entry,
                    closing_odd=close,
                    ev=ev_val,
                    beat_closing=entry > close,
                )
            )
    return bets


def walk_forward_clv(
    matches: pd.DataFrame,
    min_history: int = 100,
    xi: float = 0.0,
    ev_threshold: float = 0.0,
    retrain_every: int = 1,
) -> BacktestResult:
    """Walk-forward: para cada jogo, treina só com os ANTERIORES e avalia.

    Agrega CLV (beat_closing_rate, avg_ev) sobre as value bets e a qualidade
    probabilística (Brier/log-loss/curva de calibração, one-vs-rest agrupado)
    sobre todos os jogos avaliados.
    """
    _validate(matches)
    df = matches.sort_values("date", kind="stable").reset_index(drop=True)

    model: dc.DixonColesModel | None = None
    last_fit_at = -(10**9)

    cal_probs: list[float] = []
    cal_outcomes: list[int] = []
    bets: list[BetRecord] = []
    preds: list[dict] = []
    n_matches = 0

    for i in range(len(df)):
        if i < min_history:
            continue
        home = df.at[i, "home"]
        away = df.at[i, "away"]

        model, last_fit_at = _maybe_refit(
            df, i, model, last_fit_at, retrain_every, xi, home, away
        )
        if model is None or home not in model.attack or away not in model.attack:
            continue  # algum time ainda sem histórico → não dá para prever

        pred = model.predict(home, away)
        probs = {s: pred[_PRED_KEY[s]] for s in _SELECTIONS}
        realized = _result(df.at[i, "home_goals"], df.at[i, "away_goals"])

        # calibração one-vs-rest: 3 amostras binárias por jogo
        for sel in _SELECTIONS:
            cal_probs.append(probs[sel])
            cal_outcomes.append(1 if sel == realized else 0)

        opening = {s: float(df.at[i, f"o_{s}"]) for s in _SELECTIONS}
        closing = {s: float(df.at[i, f"c_{s}"]) for s in _SELECTIONS}
        bets.extend(evaluate_value_bets(probs, opening, closing, ev_threshold))

        preds.append(
            {
                "date": df.at[i, "date"],
                "home": home,
                "away": away,
                "p_home": probs["home"],
                "p_draw": probs["draw"],
                "p_away": probs["away"],
                "result": realized,
            }
        )
        n_matches += 1

    n_bets = len(bets)
    return BacktestResult(
        n_matches=n_matches,
        n_bets=n_bets,
        beat_closing_rate=(
            sum(b.beat_closing for b in bets) / n_bets if n_bets else None
        ),
        avg_ev=(sum(b.ev for b in bets) / n_bets if n_bets else None),
        brier=ev.brier_score(cal_probs, cal_outcomes) if cal_probs else float("nan"),
        log_loss=ev.log_loss(cal_probs, cal_outcomes) if cal_probs else float("nan"),
        calibration=ev.calibration_curve(cal_probs, cal_outcomes)
        if cal_probs
        else ([], [], []),
        match_preds=preds,
    )


def base_rate_brier(matches: pd.DataFrame, min_history: int = 100) -> float:
    """Baseline honesto: prever sempre as frequências marginais (base rates) do
    treino para cada jogo avaliado. Serve para mostrar que o modelo agrega valor.
    """
    _validate(matches)
    df = matches.sort_values("date", kind="stable").reset_index(drop=True)
    results = [
        _result(df.at[i, "home_goals"], df.at[i, "away_goals"]) for i in range(len(df))
    ]
    probs: list[float] = []
    outcomes: list[int] = []
    for i in range(min_history, len(df)):
        past = results[:i]
        rates = {s: past.count(s) / len(past) for s in _SELECTIONS}
        for sel in _SELECTIONS:
            probs.append(rates[sel])
            outcomes.append(1 if sel == results[i] else 0)
    return ev.brier_score(probs, outcomes) if probs else float("nan")


def _maybe_refit(df, i, model, last_fit_at, retrain_every, xi, home, away):
    """Refit em batch a cada `retrain_every`, ou quando um time é desconhecido."""
    needs = (
        model is None
        or (i - last_fit_at) >= retrain_every
        or home not in model.attack
        or away not in model.attack
    )
    if needs:
        train = df.iloc[:i]
        model = dc.fit(train, xi=xi)
        last_fit_at = i
    return model, last_fit_at


def _result(home_goals, away_goals) -> str:
    if home_goals > away_goals:
        return "home"
    if home_goals < away_goals:
        return "away"
    return "draw"


def _validate(matches: pd.DataFrame) -> None:
    missing = [c for c in _REQUIRED if c not in matches.columns]
    if missing:
        raise ValueError(f"colunas ausentes em matches: {missing}")
    if len(matches) == 0:
        raise ValueError("matches está vazio")
