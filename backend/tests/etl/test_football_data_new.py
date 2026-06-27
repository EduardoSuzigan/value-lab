"""ETL do feed `/new/` do football-data (Brasil): arquivo único, todas as
temporadas, SÓ odds de fechamento (sem abertura).

`parse_new` normaliza o formato novo (Home/Away/HG/AG, Season=ano civil) p/ o mesmo
schema Match/Odds das europeias, filtrando por temporada. Sem odds de abertura →
`o_*` ficam NaN (CLV não é computável p/ BRA; calibração sim — caveat do CLAUDE.md).
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from app.etl import football_data as fd

FIXTURE = Path(__file__).parent / "fixtures" / "bra_sample.csv"


def _raw() -> pd.DataFrame:
    return pd.read_csv(FIXTURE, encoding="utf-8-sig")


def test_parse_new_filters_season_and_drops_unplayed():
    out = fd.parse_new(_raw(), league="BRA", season="2025")
    # 2025 tem 3 linhas, 1 sem placar → 2 jogos
    assert len(out) == 2
    assert set(out["season"].unique()) == {"2025"}
    assert set(out["league"].unique()) == {"BRA"}
    assert list(out["home"]) == ["Palmeiras", "Corinthians"]


def test_parse_new_maps_closing_and_leaves_opening_null():
    out = fd.parse_new(_raw(), league="BRA", season="2024")
    row = out.iloc[0]
    assert row["home"] == "Flamengo" and row["away"] == "Palmeiras"
    assert row["home_goals"] == 2 and row["away_goals"] == 1
    # fechamento preenchido (AvgC preferido — melhor cobertura no feed novo)
    assert row["c_home"] == 2.35 and row["c_draw"] == 3.15 and row["c_away"] == 3.05
    # SEM abertura no feed novo → o_* NaN
    assert math.isnan(row["o_home"]) and math.isnan(row["o_away"])


def test_parse_new_output_feeds_persist_and_backtest_schema():
    from app.services.backtest import _REQUIRED

    out = fd.parse_new(_raw(), league="BRA", season="2024")
    assert set(_REQUIRED).issubset(out.columns)


def test_load_new_uses_injected_fetcher_and_filters_season():
    payload = FIXTURE.read_bytes()

    def fake_fetcher(url: str) -> bytes:
        assert url.endswith("/new/BRA.csv")  # feed único, sem temporada na URL
        return payload

    out = fd.load_new("BRA", "2024", fetcher=fake_fetcher)
    assert len(out) == 2
    assert set(out["season"].unique()) == {"2024"}


def test_parse_new_raises_without_core_columns():
    bad = _raw().drop(columns=["HG"])
    with pytest.raises(ValueError):
        fd.parse_new(bad, league="BRA", season="2024")
