"""Harness do registro de fontes por liga (etl/sources/registry.py)."""

import pytest

from app.etl.sources import registry


class TestLeagueRegistry:
    def test_e0_is_premier_league_england(self):
        src = registry.get_source("E0")
        assert src.name == "Premier League"
        assert src.country == "England"
        assert src.fd_code == "E0"
        assert src.experimental is False

    def test_unknown_league_raises(self):
        with pytest.raises(KeyError):
            registry.get_source("ZZ")

    def test_lists_registered_codes(self):
        codes = registry.codes()
        assert "E0" in codes
