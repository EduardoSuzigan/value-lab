"""Harness do parser football-data.co.uk (etl/football_data.py).

A lógica de PARSE (CSV cru → Match/Odds normalizado) é pura e testada contra uma
fixture; o download é um wrapper fino de I/O com fetcher injetável (sem rede no teste).
ETL escreve só Match/Odds — nunca Prediction (ver predictions-append-only.md).
"""

from pathlib import Path

import pandas as pd
import pytest

from app.etl import football_data as fd

FIXTURE = Path(__file__).parent / "fixtures" / "e0_sample.csv"

NORMALIZED_COLS = {
    "date", "league", "season", "home", "away", "home_goals", "away_goals",
    "o_home", "o_draw", "o_away", "c_home", "c_draw", "c_away",
}


def _raw():
    return pd.read_csv(FIXTURE, encoding="latin-1")


class TestSeasonUrl:
    def test_builds_football_data_path(self):
        url = fd.season_url("E0", "2324")
        assert url == "https://www.football-data.co.uk/mmz4281/2324/E0.csv"


class TestParse:
    def test_normalized_schema_and_dropped_unplayed(self):
        df = fd.parse(_raw(), league="E0", season="2324")
        assert set(df.columns) == NORMALIZED_COLS
        assert len(df) == 4  # a 5ª linha (sem placar) é jogo futuro → descartada
        assert df["league"].unique().tolist() == ["E0"]
        assert df["season"].unique().tolist() == ["2324"]

    def test_types_and_date_parsing(self):
        df = fd.parse(_raw(), league="E0", season="2324").reset_index(drop=True)
        assert pd.api.types.is_integer_dtype(df["home_goals"])
        assert pd.api.types.is_datetime64_any_dtype(df["date"])
        # 11/08/2023 = 11 de agosto (dayfirst)
        assert df.loc[0, "date"] == pd.Timestamp("2023-08-11")
        assert df.loc[0, "home"] == "Burnley"
        assert df.loc[0, "home_goals"] == 0 and df.loc[0, "away_goals"] == 3

    def test_maps_opening_and_closing_odds(self):
        df = fd.parse(_raw(), league="E0", season="2324").reset_index(drop=True)
        # B365 é a preferência: abertura B365H/D/A, fechamento B365CH/CD/CA
        assert df.loc[0, "o_home"] == pytest.approx(7.50)
        assert df.loc[0, "o_away"] == pytest.approx(1.40)
        assert df.loc[0, "c_home"] == pytest.approx(8.00)
        assert df.loc[0, "c_away"] == pytest.approx(1.36)

    def test_falls_back_to_average_when_b365_absent(self):
        raw = _raw().drop(
            columns=["B365H", "B365D", "B365A", "B365CH", "B365CD", "B365CA"]
        )
        df = fd.parse(raw, league="E0", season="2324").reset_index(drop=True)
        assert df.loc[0, "o_home"] == pytest.approx(7.10)  # AvgH
        assert df.loc[0, "c_home"] == pytest.approx(7.80)  # AvgCH

    def test_raises_when_no_odds_columns(self):
        raw = _raw()[["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]]
        with pytest.raises(ValueError):
            fd.parse(raw, league="E0", season="2324")

    def test_raises_when_core_column_missing(self):
        raw = _raw().drop(columns=["HomeTeam"])
        with pytest.raises(ValueError):
            fd.parse(raw, league="E0", season="2324")

    def test_output_feeds_backtest_schema(self):
        # As colunas normalizadas batem com o que o backtest espera consumir.
        from app.services import backtest as bt

        df = fd.parse(_raw(), league="E0", season="2324")
        for col in ("date", "home", "away", "home_goals", "away_goals"):
            assert col in df.columns
        for sel in ("home", "draw", "away"):
            assert f"o_{sel}" in df.columns and f"c_{sel}" in df.columns
        # validação do backtest aceita o schema (não deve levantar por colunas)
        bt._validate(df)


class TestLoadComposesDownloadAndParse:
    def test_load_uses_injected_fetcher(self):
        raw_bytes = FIXTURE.read_bytes()

        def fake_fetcher(url: str) -> bytes:
            assert "E0" in url and "2324" in url
            return raw_bytes

        df = fd.load("E0", "2324", fetcher=fake_fetcher)
        assert len(df) == 4
        assert df["league"].iloc[0] == "E0"
