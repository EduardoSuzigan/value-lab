"""Value betting: devig, expected value e Kelly fracionado.

Domínio PURO — sem I/O, sem SQL, sem rede. Recebe números, devolve números.
Convenção: odds são DECIMAIS (ex.: 2.50). Probabilidades em [0, 1].
"""

from __future__ import annotations

from collections.abc import Sequence


def implied_prob(odd: float) -> float:
    """Probabilidade implícita (com vig) de uma odd decimal: 1/odd."""
    if odd <= 1.0:
        raise ValueError(f"odd decimal deve ser > 1.0, recebido {odd!r}")
    return 1.0 / odd


def overround(odds: Sequence[float]) -> float:
    """Margem do book (vig): soma das probabilidades implícitas menos 1."""
    if not odds:
        raise ValueError("odds não pode ser vazio")
    return sum(implied_prob(o) for o in odds) - 1.0


def remove_vig(odds: Sequence[float]) -> list[float]:
    """Remove o vig normalizando as inversas (método proporcional).

    Devolve probabilidades justas que somam 1.0, na mesma ordem das odds.
    """
    if not odds:
        raise ValueError("odds não pode ser vazio")
    inv = [implied_prob(o) for o in odds]
    total = sum(inv)
    return [q / total for q in inv]


def expected_value(prob: float, odd: float, stake: float = 1.0) -> float:
    """EV de fazer back na odd decimal com probabilidade real `prob`.

    Por unidade apostada: prob*odd - 1 (lucro líquido esperado).
    """
    _check_prob(prob)
    if odd <= 1.0:
        raise ValueError(f"odd decimal deve ser > 1.0, recebido {odd!r}")
    return stake * (prob * odd - 1.0)


def kelly_fraction(prob: float, odd: float, fraction: float = 0.25) -> float:
    """Stake recomendado como fração da banca via Kelly FRACIONADO.

    Kelly cheio: f* = (b*p - q)/b, com b=odd-1, q=1-p. Multiplicado por `fraction`
    (default 25%, CLAUDE.md: NUNCA Kelly cheio). Sem edge → 0.0 (não aposta;
    nunca devolve negativo).
    """
    _check_prob(prob)
    if odd <= 1.0:
        raise ValueError(f"odd decimal deve ser > 1.0, recebido {odd!r}")
    b = odd - 1.0
    q = 1.0 - prob
    full = (b * prob - q) / b
    if full <= 0.0:
        return 0.0
    return full * fraction


def _check_prob(prob: float) -> None:
    if not 0.0 <= prob <= 1.0:
        raise ValueError(f"probabilidade deve estar em [0, 1], recebido {prob!r}")
