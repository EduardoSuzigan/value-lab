"""Harness do dixon_coles.py — modelo Poisson bivariado com correção de placares
baixos (rho) e decaimento temporal (xi), ajustado por MLE.

Dois níveis de teste:
1. Predição com parâmetros CONHECIDOS (fixa a matemática: matriz, τ, 1X2/OU/BTTS).
2. Recuperação de forças SINTÉTICAS conhecidas via fit (o gate honesto da Fase 0).
"""

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import poisson

from app.domain import dixon_coles as dc


def _model():
    """Modelo de 2 times com parâmetros conhecidos (rho=0 salvo override)."""
    return dc.DixonColesModel(
        teams=["A", "B"],
        attack={"A": 0.2, "B": -0.2},
        defense={"A": -0.1, "B": 0.1},
        home_adv=0.3,
        rho=0.0,
    )


class TestExpectedGoals:
    def test_home_and_away_lambda(self):
        m = _model()
        lam, mu = m.expected_goals("A", "B")
        # lam = exp(att_A + def_B + home); mu = exp(att_B + def_A)
        assert lam == pytest.approx(math.exp(0.2 + 0.1 + 0.3))
        assert mu == pytest.approx(math.exp(-0.2 - 0.1))


class TestScoreMatrix:
    def test_independent_poisson_when_rho_zero(self):
        m = _model()
        lam, mu = m.expected_goals("A", "B")
        mat = m.score_matrix("A", "B", max_goals=10, normalize=False)
        # rho=0 → produto de Poissons independentes
        assert mat[0, 0] == pytest.approx(poisson.pmf(0, lam) * poisson.pmf(0, mu))
        assert mat[2, 1] == pytest.approx(poisson.pmf(2, lam) * poisson.pmf(1, mu))

    def test_normalized_matrix_sums_to_one(self):
        m = _model()
        mat = m.score_matrix("A", "B", max_goals=15, normalize=True)
        assert mat.sum() == pytest.approx(1.0)

    def test_tau_correction_on_low_scores(self):
        m = dc.DixonColesModel(
            teams=["A", "B"],
            attack={"A": 0.2, "B": -0.2},
            defense={"A": -0.1, "B": 0.1},
            home_adv=0.3,
            rho=0.1,
        )
        lam, mu = m.expected_goals("A", "B")
        mat = m.score_matrix("A", "B", max_goals=10, normalize=False)
        p = lambda x, y: poisson.pmf(x, lam) * poisson.pmf(y, mu)  # noqa: E731
        assert mat[0, 0] == pytest.approx((1 - lam * mu * 0.1) * p(0, 0))
        assert mat[0, 1] == pytest.approx((1 + lam * 0.1) * p(0, 1))
        assert mat[1, 0] == pytest.approx((1 + mu * 0.1) * p(1, 0))
        assert mat[1, 1] == pytest.approx((1 - 0.1) * p(1, 1))
        # placar fora da correção fica inalterado
        assert mat[2, 2] == pytest.approx(p(2, 2))


class TestPredict:
    def test_probabilities_form_distribution(self):
        m = _model()
        pred = m.predict("A", "B")
        assert pred["home_win"] + pred["draw"] + pred["away_win"] == pytest.approx(1.0)
        assert pred["over_2_5"] + pred["under_2_5"] == pytest.approx(1.0)
        for k in ("home_win", "draw", "away_win", "over_2_5", "under_2_5", "btts"):
            assert 0.0 <= pred[k] <= 1.0

    def test_symmetric_teams_have_equal_win_probs(self):
        m = dc.DixonColesModel(
            teams=["A", "B"],
            attack={"A": 0.0, "B": 0.0},
            defense={"A": 0.0, "B": 0.0},
            home_adv=0.0,  # sem vantagem de casa → simétrico
            rho=0.0,
        )
        pred = m.predict("A", "B")
        assert pred["home_win"] == pytest.approx(pred["away_win"], abs=1e-9)

    def test_home_advantage_raises_home_win(self):
        m = _model()  # home_adv=0.3
        pred = m.predict("A", "B")
        assert pred["home_win"] > pred["away_win"]


class TestFitRecoversSyntheticStrengths:
    """O gate honesto: gerar dados de forças conhecidas e recuperá-las via MLE."""

    @staticmethod
    def _synthetic_matches(seed: int = 7, reps: int = 300):
        teams = ["T0", "T1", "T2", "T3", "T4"]
        true_att = dict(zip(teams, [0.4, 0.2, 0.0, -0.2, -0.4], strict=True))
        true_def = dict(zip(teams, [-0.2, -0.1, 0.0, 0.1, 0.2], strict=True))
        home_adv = 0.3
        rng = np.random.default_rng(seed)
        rows = []
        for i in teams:
            for j in teams:
                if i == j:
                    continue
                lam = math.exp(true_att[i] + true_def[j] + home_adv)
                mu = math.exp(true_att[j] + true_def[i])
                hg = rng.poisson(lam, reps)
                ag = rng.poisson(mu, reps)
                for k in range(reps):
                    rows.append((i, j, int(hg[k]), int(ag[k])))
        df = pd.DataFrame(rows, columns=["home", "away", "home_goals", "away_goals"])
        return df, true_att, true_def, home_adv

    def test_recovers_attack_defense_and_home(self):
        df, true_att, true_def, home_adv = self._synthetic_matches()
        model = dc.fit(df, xi=0.0)

        teams = ["T0", "T1", "T2", "T3", "T4"]
        rec_att = np.array([model.attack[t] for t in teams])
        rec_def = np.array([model.defense[t] for t in teams])
        exp_att = np.array([true_att[t] for t in teams])
        exp_def = np.array([true_def[t] for t in teams])

        # gauge fixado: média do ataque = 0 (igual aos sintéticos)
        assert rec_att.mean() == pytest.approx(0.0, abs=1e-6)
        assert np.max(np.abs(rec_att - exp_att)) < 0.08
        assert np.max(np.abs(rec_def - exp_def)) < 0.08
        assert model.home_adv == pytest.approx(home_adv, abs=0.06)
        assert model.rho == pytest.approx(0.0, abs=0.05)

    def test_preserves_attack_ranking(self):
        df, true_att, _, _ = self._synthetic_matches()
        model = dc.fit(df, xi=0.0)
        teams = ["T0", "T1", "T2", "T3", "T4"]
        rec = [model.attack[t] for t in teams]
        # T0 mais forte ... T4 mais fraco
        assert rec == sorted(rec, reverse=True)


class TestScoreMatrixStaysNonNegative:
    """rho no extremo + placar alto faria tau(0,0) < 0 — a matriz não pode ter
    células negativas nem produzir probabilidades fora de [0, 1]."""

    def test_extreme_rho_high_scoring_is_valid_distribution(self):
        m = dc.DixonColesModel(
            teams=["A", "B"],
            attack={"A": 0.9, "B": 0.9},
            defense={"A": 0.9, "B": 0.9},
            home_adv=0.3,
            rho=0.2,
        )
        lam, mu = m.expected_goals("A", "B")
        assert lam * mu * 0.2 > 1.0  # confirma que tau(0,0) cru seria negativo

        mat = m.score_matrix("A", "B", max_goals=10, normalize=False)
        assert (mat >= 0).all()

        pred = m.predict("A", "B")
        for v in pred.values():
            assert 0.0 <= v <= 1.0
        assert pred["home_win"] + pred["draw"] + pred["away_win"] == pytest.approx(1.0)


class TestTemporalDecay:
    """Exercita o decaimento temporal xi (antes sem cobertura): com recência forte,
    o ajuste deve seguir o regime recente, não a média de todo o histórico."""

    @staticmethod
    def _phase(rng, att_t0, n_rounds, start_day):
        teams = ["T0", "T1", "T2"]
        att = {"T0": att_t0, "T1": 0.0, "T2": 0.0}
        rows = []
        day = start_day
        for _ in range(n_rounds):
            for i in teams:
                for j in teams:
                    if i == j:
                        continue
                    lam = math.exp(att[i] + 0.2)  # def=0, home_adv=0.2
                    mu = math.exp(att[j])
                    rows.append(
                        (day, i, j, int(rng.poisson(lam)), int(rng.poisson(mu)))
                    )
                    day += pd.Timedelta(days=1)
        return rows, day

    def test_recency_weighting_pulls_strength_to_recent_regime(self):
        rng = np.random.default_rng(3)
        old, day = self._phase(
            rng, att_t0=-0.6, n_rounds=8, start_day=pd.Timestamp("2024-01-01")
        )
        new, _ = self._phase(rng, att_t0=0.6, n_rounds=8, start_day=day)
        cols = ["date", "home", "away", "home_goals", "away_goals"]
        df = pd.DataFrame(old + new, columns=cols)

        flat = dc.fit(df, xi=0.0)
        recent = dc.fit(df, xi=0.05)
        # T0 era fraco no passado e forte no presente → recência eleva seu ataque
        assert recent.attack["T0"] > flat.attack["T0"]


class TestFitValidation:
    def test_rejects_missing_columns(self):
        df = pd.DataFrame({"home": ["A"], "away": ["B"]})
        with pytest.raises(ValueError):
            dc.fit(df)

    def test_rejects_empty(self):
        df = pd.DataFrame(columns=["home", "away", "home_goals", "away_goals"])
        with pytest.raises(ValueError):
            dc.fit(df)
