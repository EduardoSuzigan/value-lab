"""Modelo Dixon-Coles: Poisson bivariado de gols com correção de placares baixos
(rho) e decaimento temporal (xi), ajustado por máxima verossimilhança (L-BFGS-B).

Domínio PURO (numpy/scipy, sem I/O). O fit é SEMPRE por (liga, temporada) — este
módulo recebe um DataFrame de partidas de UMA liga e devolve um modelo. Nunca faça
pooling entre ligas (ver .claude/rules/per-league-fit.md).

Parametrização:
    lambda (gols casa)  = exp(att_home + def_away + home_adv)
    mu     (gols fora)  = exp(att_away + def_home)
Gauge fixado por média(att) = 0 (remove a degenerescência att_i + def_j).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

_REQUIRED_COLS = ("home", "away", "home_goals", "away_goals")
_TAU_EPS = 1e-10


def _tau(x, y, lam, mu, rho):
    """Correção Dixon-Coles para placares baixos (vetorizada)."""
    t = np.ones_like(lam, dtype=float)
    m00 = (x == 0) & (y == 0)
    m01 = (x == 0) & (y == 1)
    m10 = (x == 1) & (y == 0)
    m11 = (x == 1) & (y == 1)
    t = np.where(m00, 1.0 - lam * mu * rho, t)
    t = np.where(m01, 1.0 + lam * rho, t)
    t = np.where(m10, 1.0 + mu * rho, t)
    t = np.where(m11, 1.0 - rho, t)
    return t


@dataclass
class DixonColesModel:
    teams: list[str]
    attack: dict[str, float]
    defense: dict[str, float]
    home_adv: float
    rho: float

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        """(lambda, mu) — gols esperados de casa e fora."""
        lam = np.exp(self.attack[home] + self.defense[away] + self.home_adv)
        mu = np.exp(self.attack[away] + self.defense[home])
        return float(lam), float(mu)

    def score_matrix(
        self, home: str, away: str, max_goals: int = 10, normalize: bool = True
    ) -> np.ndarray:
        """P(placar) numa grade (max_goals+1)×(max_goals+1): linhas=gols casa."""
        lam, mu = self.expected_goals(home, away)
        gx = np.arange(max_goals + 1)
        px = np.exp(gx * np.log(lam) - lam - gammaln(gx + 1))
        py = np.exp(gx * np.log(mu) - mu - gammaln(gx + 1))
        mat = np.outer(px, py)
        # correção de placares baixos
        for x, y in ((0, 0), (0, 1), (1, 0), (1, 1)):
            mat[x, y] *= _tau(
                np.array(x), np.array(y), np.array(lam), np.array(mu), self.rho
            )
        if normalize:
            mat = mat / mat.sum()
        return mat

    def predict(self, home: str, away: str, max_goals: int = 10) -> dict[str, float]:
        """Probabilidades dos mercados: 1X2, Over/Under 2.5 e BTTS."""
        mat = self.score_matrix(home, away, max_goals=max_goals, normalize=True)
        gx = np.arange(max_goals + 1)
        x = gx[:, None]
        y = gx[None, :]
        total = x + y
        return {
            "home_win": float(mat[x > y].sum()),
            "draw": float(mat[x == y].sum()),
            "away_win": float(mat[x < y].sum()),
            "over_2_5": float(mat[total >= 3].sum()),
            "under_2_5": float(mat[total <= 2].sum()),
            "btts": float(mat[(x >= 1) & (y >= 1)].sum()),
        }


def fit(
    matches: pd.DataFrame,
    xi: float = 0.0,
    ref_date=None,
) -> DixonColesModel:
    """Ajusta Dixon-Coles a partidas de UMA liga por MLE.

    `matches`: DataFrame com colunas home, away, home_goals, away_goals e,
    opcionalmente, `date` (para o decaimento temporal). `xi` é a taxa de
    decaimento (0 = sem decaimento). Cada partida pesa exp(-xi * idade_em_dias).
    """
    _validate(matches)

    teams = sorted(set(matches["home"]) | set(matches["away"]))
    n = len(teams)
    tidx = {t: i for i, t in enumerate(teams)}

    hi = matches["home"].map(tidx).to_numpy()
    ai = matches["away"].map(tidx).to_numpy()
    x = matches["home_goals"].to_numpy(dtype=float)
    y = matches["away_goals"].to_numpy(dtype=float)
    w = _decay_weights(matches, xi, ref_date)

    # termos constantes do log-Poisson (não afetam o argmin, mas dão nll honesto)
    const = -(gammaln(x + 1) + gammaln(y + 1))

    # vetor de parâmetros livres: att_free (n-1), def (n), home_adv, rho
    def unpack(p):
        att_free = p[: n - 1]
        attack = np.concatenate([att_free, [-att_free.sum()]])  # gauge: soma=0
        defense = p[n - 1 : 2 * n - 1]
        home_adv = p[2 * n - 1]
        rho = p[2 * n]
        return attack, defense, home_adv, rho

    def neg_log_lik(p):
        attack, defense, home_adv, rho = unpack(p)
        log_lam = attack[hi] + defense[ai] + home_adv
        log_mu = attack[ai] + defense[hi]
        lam = np.exp(log_lam)
        mu = np.exp(log_mu)
        log_pois = x * log_lam - lam + y * log_mu - mu + const
        tau = _tau(x, y, lam, mu, rho)
        log_tau = np.log(np.clip(tau, _TAU_EPS, None))
        return -np.sum(w * (log_pois + log_tau))

    p0 = np.zeros(2 * n + 1)
    p0[2 * n - 1] = 0.25  # palpite inicial de vantagem de casa
    bounds = (
        [(-3.0, 3.0)] * (n - 1)  # att_free
        + [(-3.0, 3.0)] * n  # def
        + [(-1.0, 2.0)]  # home_adv
        + [(-0.2, 0.2)]  # rho (mantém tau > 0)
    )

    res = minimize(neg_log_lik, p0, method="L-BFGS-B", bounds=bounds)
    attack, defense, home_adv, rho = unpack(res.x)

    return DixonColesModel(
        teams=teams,
        attack={t: float(attack[i]) for t, i in tidx.items()},
        defense={t: float(defense[i]) for t, i in tidx.items()},
        home_adv=float(home_adv),
        rho=float(rho),
    )


def _validate(matches: pd.DataFrame) -> None:
    missing = [c for c in _REQUIRED_COLS if c not in matches.columns]
    if missing:
        raise ValueError(f"colunas ausentes em matches: {missing}")
    if len(matches) == 0:
        raise ValueError("matches está vazio")


def _decay_weights(matches: pd.DataFrame, xi: float, ref_date) -> np.ndarray:
    if xi == 0.0 or "date" not in matches.columns:
        return np.ones(len(matches), dtype=float)
    dates = pd.to_datetime(matches["date"])
    ref = pd.to_datetime(ref_date) if ref_date is not None else dates.max()
    age_days = (ref - dates).dt.total_seconds().to_numpy() / 86400.0
    return np.exp(-xi * np.clip(age_days, 0.0, None))


__all__: Sequence[str] = ["DixonColesModel", "fit"]
