"""Harness do value.py — devig, EV, Kelly fracionado. Funções puras (sem I/O)."""


import pytest

from app.domain import value


class TestImpliedProb:
    def test_inverse_of_decimal_odd(self):
        assert value.implied_prob(2.0) == pytest.approx(0.5)
        assert value.implied_prob(4.0) == pytest.approx(0.25)

    def test_rejects_odds_below_one(self):
        with pytest.raises(ValueError):
            value.implied_prob(0.9)


class TestRemoveVig:
    def test_two_way_market_normalizes_to_one(self):
        fair = value.remove_vig([1.5, 2.5])
        assert sum(fair) == pytest.approx(1.0)
        assert fair[0] == pytest.approx(0.625)
        assert fair[1] == pytest.approx(0.375)

    def test_fair_market_unchanged(self):
        fair = value.remove_vig([2.0, 2.0])
        assert fair == pytest.approx([0.5, 0.5])

    def test_1x2_market_sums_to_one(self):
        fair = value.remove_vig([1.90, 3.50, 4.50])
        assert sum(fair) == pytest.approx(1.0)
        assert len(fair) == 3
        # ordem preservada: casa é o mais provável
        assert fair[0] > fair[1] > fair[2]

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            value.remove_vig([])


class TestOverround:
    def test_fair_market_is_zero(self):
        assert value.overround([2.0, 2.0]) == pytest.approx(0.0)

    def test_vig_market_is_positive(self):
        assert value.overround([1.5, 2.5]) == pytest.approx(0.06666667)


class TestExpectedValue:
    def test_positive_edge(self):
        # p=0.6 @ 2.0 → 0.6*2 - 1 = 0.2 por unidade apostada
        assert value.expected_value(0.6, 2.0) == pytest.approx(0.2)

    def test_fair_bet_is_zero(self):
        assert value.expected_value(0.5, 2.0) == pytest.approx(0.0)

    def test_negative_edge(self):
        assert value.expected_value(0.4, 2.0) == pytest.approx(-0.2)


class TestKellyFraction:
    def test_full_kelly_positive_edge(self):
        # f* = (b*p - q)/b, b=1, p=0.6, q=0.4 → 0.2
        assert value.kelly_fraction(0.6, 2.0, fraction=1.0) == pytest.approx(0.2)

    def test_default_is_quarter_kelly(self):
        # default 25% (CLAUDE.md: Kelly fracionado, NUNCA cheio)
        assert value.kelly_fraction(0.6, 2.0) == pytest.approx(0.05)

    def test_no_edge_returns_zero(self):
        assert value.kelly_fraction(0.5, 2.0) == 0.0

    def test_negative_edge_returns_zero_not_negative(self):
        # nunca recomenda apostar contra (no laying aqui)
        assert value.kelly_fraction(0.4, 2.0) == 0.0

    def test_fraction_scales_linearly(self):
        full = value.kelly_fraction(0.6, 2.0, fraction=1.0)
        half = value.kelly_fraction(0.6, 2.0, fraction=0.5)
        assert half == pytest.approx(full * 0.5)

    def test_rejects_invalid_probability(self):
        with pytest.raises(ValueError):
            value.kelly_fraction(1.5, 2.0)
