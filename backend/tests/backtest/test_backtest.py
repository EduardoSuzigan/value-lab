"""Harness do backtest walk-forward de CLV + calibração (services/backtest.py).

Critério honesto: CLV (modelo vs. linha de FECHAMENTO), nunca ROI no histórico.
Dois níveis:
1. evaluate_value_bets — aritmética pura de EV / value / beat_closing.
2. walk_forward_clv — só treina com o passado (sem vazamento), agrega CLV e
   calibração. A calibração precisa bater base rates; o CLV fica em faixa válida.
"""

import math

import numpy as np
import pandas as pd
import pytest

from app.domain import dixon_coles as dc
from app.services import backtest as bt


class TestEvaluateValueBets:
    def test_flags_only_positive_ev(self):
        probs = {"home": 0.60, "draw": 0.25, "away": 0.15}
        opening = {"home": 2.0, "draw": 4.0, "away": 5.0}
        closing = {"home": 1.8, "draw": 4.2, "away": 5.5}
        bets = bt.evaluate_value_bets(probs, opening, closing, ev_threshold=0.0)
        # home: 0.6*2-1=0.2 (>0, flag); draw: 0.25*4-1=0 (não); away: 0.15*5-1=-0.25
        assert [b.selection for b in bets] == ["home"]
        assert bets[0].ev == pytest.approx(0.2)

    def test_beat_closing_when_entry_odd_higher(self):
        probs = {"home": 0.60, "draw": 0.25, "away": 0.15}
        opening = {"home": 2.0, "draw": 4.0, "away": 5.0}
        closing = {"home": 1.8, "draw": 4.2, "away": 5.5}
        bet = bt.evaluate_value_bets(probs, opening, closing)[0]
        assert (
            bet.beat_closing is True
        )  # 2.0 > 1.8 → preço de entrada melhor que o close
        assert bet.entry_odd == 2.0
        assert bet.closing_odd == 1.8

    def test_no_beat_closing_when_market_shortened_against_us(self):
        probs = {"home": 0.60, "draw": 0.25, "away": 0.15}
        opening = {"home": 2.0, "draw": 4.0, "away": 5.0}
        closing = {"home": 2.2, "draw": 4.0, "away": 5.0}  # fechou mais alto
        bet = bt.evaluate_value_bets(probs, opening, closing)[0]
        assert bet.beat_closing is False

    def test_threshold_filters_marginal_bets(self):
        probs = {"home": 0.55, "draw": 0.25, "away": 0.20}
        opening = {"home": 2.0, "draw": 4.0, "away": 5.0}
        closing = {"home": 2.0, "draw": 4.0, "away": 5.0}
        # home ev=0.1; com threshold 0.15 não deve passar
        assert bt.evaluate_value_bets(probs, opening, closing, ev_threshold=0.15) == []
        assert (
            len(bt.evaluate_value_bets(probs, opening, closing, ev_threshold=0.05)) == 1
        )


# ----------------------------------------------------------------------------- #
# Fixtures sintéticas: liga gerada por um Dixon-Coles conhecido + odds de mercado.
# ----------------------------------------------------------------------------- #


def _true_model():
    teams = ["T0", "T1", "T2", "T3", "T4", "T5"]
    att = dict(zip(teams, [0.5, 0.3, 0.1, -0.1, -0.3, -0.5], strict=True))
    dfn = dict(zip(teams, [-0.3, -0.15, 0.0, 0.0, 0.15, 0.3], strict=True))
    return dc.DixonColesModel(teams, att, dfn, home_adv=0.3, rho=-0.05)


def _odds_from_probs(p_true, rng, margin=0.05, open_noise=0.04):
    """Closing ≈ probs verdadeiras (com vig); opening = versão ruidosa."""
    sels = ["home", "draw", "away"]
    pt = np.array([p_true["home_win"], p_true["draw"], p_true["away_win"]])
    closing = {s: float(1.0 / (pt[i] * (1 + margin))) for i, s in enumerate(sels)}
    po = np.clip(pt + rng.normal(0, open_noise, 3), 1e-3, None)
    po = po / po.sum()
    opening = {s: float(1.0 / (po[i] * (1 + margin))) for i, s in enumerate(sels)}
    return opening, closing


def _synth_league(seed=11, seasons=4):
    model = _true_model()
    teams = model.teams
    rng = np.random.default_rng(seed)
    rows = []
    day = pd.Timestamp("2023-01-01")
    for _season in range(seasons):
        for i in teams:
            for j in teams:
                if i == j:
                    continue
                lam, mu = model.expected_goals(i, j)
                hg, ag = int(rng.poisson(lam)), int(rng.poisson(mu))
                p = model.predict(i, j)
                opening, closing = _odds_from_probs(p, rng)
                rows.append(
                    {
                        "date": day,
                        "home": i,
                        "away": j,
                        "home_goals": hg,
                        "away_goals": ag,
                        "o_home": opening["home"],
                        "o_draw": opening["draw"],
                        "o_away": opening["away"],
                        "c_home": closing["home"],
                        "c_draw": closing["draw"],
                        "c_away": closing["away"],
                    }
                )
                day += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


class TestWalkForwardMechanics:
    def test_skips_until_min_history_then_backtests_rest(self):
        df = _synth_league()
        res = bt.walk_forward_clv(df, min_history=60, retrain_every=15)
        assert 0 < res.n_matches < len(df)  # início pulado, resto avaliado

    def test_metrics_in_valid_ranges(self):
        df = _synth_league()
        res = bt.walk_forward_clv(df, min_history=60, retrain_every=15)
        assert 0.0 <= res.brier <= 1.0
        assert res.log_loss >= 0.0 and math.isfinite(res.log_loss)
        if res.n_bets > 0:
            assert 0.0 <= res.beat_closing_rate <= 1.0
            assert math.isfinite(res.avg_ev)
        assert len(res.calibration[0]) > 0  # curva de calibração não vazia


class TestNoLeakage:
    def test_future_results_do_not_affect_past_predictions(self):
        df = _synth_league()
        res_a = bt.walk_forward_clv(df, min_history=60, retrain_every=1)

        # corrompe o ÚLTIMO jogo; predições dos jogos anteriores devem ser idênticas
        df2 = df.copy()
        df2.loc[df2.index[-1], "home_goals"] = 9
        df2.loc[df2.index[-1], "away_goals"] = 0
        res_b = bt.walk_forward_clv(df2, min_history=60, retrain_every=1)

        preds_a = {
            (p["home"], p["away"], p["date"]): p["p_home"]
            for p in res_a.match_preds[:-1]
        }
        preds_b = {
            (p["home"], p["away"], p["date"]): p["p_home"]
            for p in res_b.match_preds[:-1]
        }
        assert preds_a.keys() == preds_b.keys()
        for k in preds_a:
            assert preds_a[k] == pytest.approx(preds_b[k])


class TestCalibrationBeatsBaseRates:
    def test_model_brier_better_than_predicting_base_rates(self):
        df = _synth_league(seasons=4)
        res = bt.walk_forward_clv(df, min_history=60, retrain_every=10)

        # baseline: prever sempre a frequência marginal (base rates) do treino
        baseline_brier = bt.base_rate_brier(df, min_history=60)
        assert res.brier < baseline_brier


class TestValidation:
    def test_rejects_missing_odds_columns(self):
        df = _synth_league().drop(columns=["c_home"])
        with pytest.raises(ValueError):
            bt.walk_forward_clv(df, min_history=60)


class TestClosingOnlyLeague:
    """Ligas sem odds de abertura (ex.: Brasil/feed novo): o walk-forward não pode
    quebrar e não há value bets (sem preço de entrada → sem CLV); a calibração,
    que não usa odds, continua válida."""

    def test_missing_opening_odds_yields_calibration_but_no_bets(self):
        df = _synth_league(seed=7, seasons=4)
        # load_matches_df devolve None (SQL NULL) p/ ligas sem abertura — não NaN
        df[["o_home", "o_draw", "o_away"]] = None

        res = bt.walk_forward_clv(df, min_history=60, retrain_every=10)

        assert res.n_bets == 0
        assert res.beat_closing_rate is None
        assert res.avg_ev is None
        assert not math.isnan(res.brier)  # calibração calculada normalmente
        assert res.n_matches > 0
