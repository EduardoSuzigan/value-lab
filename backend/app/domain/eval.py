"""Avaliação probabilística: Brier, log-loss e curva de calibração.

Domínio PURO (matemática com numpy, sem I/O). Métricas honestas de "minhas
probabilidades são confiáveis?" — complementam o CLV. Binário: `probs` = P(evento),
`outcomes` ∈ {0, 1}.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def _as_pair(probs: Sequence[float], outcomes: Sequence[int]) -> tuple:
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if p.shape != y.shape:
        raise ValueError(
            f"probs {p.shape} e outcomes {y.shape} têm tamanhos diferentes"
        )
    if p.size == 0:
        raise ValueError("probs/outcomes não podem ser vazios")
    return p, y


def brier_score(probs: Sequence[float], outcomes: Sequence[int]) -> float:
    """Brier score binário: média de (p - y)². Em [0, 1], menor é melhor."""
    p, y = _as_pair(probs, outcomes)
    return float(np.mean((p - y) ** 2))


def log_loss(
    probs: Sequence[float], outcomes: Sequence[int], eps: float = 1e-15
) -> float:
    """Log-loss (entropia cruzada binária). Clipa em [eps, 1-eps] (evita ±inf)."""
    p, y = _as_pair(probs, outcomes)
    p = np.clip(p, eps, 1.0 - eps)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def calibration_curve(
    probs: Sequence[float], outcomes: Sequence[int], n_bins: int = 10
) -> tuple[list[float], list[float], list[int]]:
    """Agrupa predições em `n_bins` faixas iguais de [0, 1].

    Devolve (prob_pred, prob_true, counts) apenas dos bins NÃO vazios:
    - prob_pred: probabilidade média prevista no bin.
    - prob_true: fração observada de positivos no bin.
    - counts: nº de amostras no bin.
    Calibração perfeita ⇔ prob_true ≈ prob_pred.
    """
    p, y = _as_pair(probs, outcomes)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # bin por amostra; o limite superior 1.0 entra no último bin
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, n_bins - 1)

    prob_pred: list[float] = []
    prob_true: list[float] = []
    counts: list[int] = []
    for b in range(n_bins):
        mask = idx == b
        n = int(mask.sum())
        if n == 0:
            continue
        prob_pred.append(float(p[mask].mean()))
        prob_true.append(float(y[mask].mean()))
        counts.append(n)
    return prob_pred, prob_true, counts
