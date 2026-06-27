"""Harness do eval.py — métricas honestas de qualidade probabilística.

Brier, log-loss e curva de calibração. O critério de ciência de dados do projeto:
"quando o modelo diz 60%, acontece ~60%?".
"""

import math

import pytest

from app.domain import eval as ev


class TestBrierScore:
    def test_perfect_predictions_score_zero(self):
        assert ev.brier_score([1.0, 0.0, 1.0], [1, 0, 1]) == pytest.approx(0.0)

    def test_worst_predictions_score_one(self):
        assert ev.brier_score([0.0, 1.0], [1, 0]) == pytest.approx(1.0)

    def test_known_value(self):
        # ((0.6-1)^2 + (0.4-0)^2) / 2 = (0.16 + 0.16)/2 = 0.16
        assert ev.brier_score([0.6, 0.4], [1, 0]) == pytest.approx(0.16)

    def test_always_half_scores_quarter(self):
        assert ev.brier_score([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0]) == pytest.approx(0.25)

    def test_rejects_length_mismatch(self):
        with pytest.raises(ValueError):
            ev.brier_score([0.5, 0.5], [1])


class TestLogLoss:
    def test_known_value(self):
        # y=1,p=0.6 → -log(0.6); y=0,p=0.4 → -log(0.6); média = -log(0.6)
        assert ev.log_loss([0.6, 0.4], [1, 0]) == pytest.approx(-math.log(0.6))

    def test_confident_correct_is_near_zero(self):
        assert ev.log_loss([0.999, 0.001], [1, 0]) == pytest.approx(0.0, abs=1e-2)

    def test_clips_to_avoid_infinity(self):
        # p=0 quando y=1 seria -inf; o clip deve mantê-lo finito e grande
        loss = ev.log_loss([0.0], [1])
        assert math.isfinite(loss)
        assert loss > 10

    def test_rejects_length_mismatch(self):
        with pytest.raises(ValueError):
            ev.log_loss([0.5], [1, 0])


class TestCalibrationCurve:
    def test_perfectly_calibrated_bins(self):
        probs = [0.25] * 4 + [0.75] * 4
        outcomes = [1, 0, 0, 0, 1, 1, 1, 0]  # 25% e 75% positivos
        prob_pred, prob_true, counts = ev.calibration_curve(probs, outcomes, n_bins=10)
        assert prob_pred == pytest.approx([0.25, 0.75])
        assert prob_true == pytest.approx([0.25, 0.75])
        assert list(counts) == [4, 4]

    def test_only_returns_non_empty_bins(self):
        probs = [0.05, 0.05, 0.95, 0.95]
        outcomes = [0, 0, 1, 1]
        prob_pred, prob_true, counts = ev.calibration_curve(probs, outcomes, n_bins=10)
        assert len(prob_pred) == 2  # só os 2 bins ocupados

    def test_handles_prob_at_boundary_one(self):
        prob_pred, prob_true, counts = ev.calibration_curve([1.0], [1], n_bins=10)
        assert counts[0] == 1
        assert prob_true[0] == pytest.approx(1.0)

    def test_rejects_length_mismatch(self):
        with pytest.raises(ValueError):
            ev.calibration_curve([0.5, 0.5], [1], n_bins=5)
