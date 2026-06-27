"""ETL do football-data.co.uk → Match/Odds normalizados (uma liga, uma temporada).

Camada ETL: faz I/O (download) e normalização. NUNCA escreve em Prediction/ModelRun
(ver .claude/rules/predictions-append-only.md). A lógica de `parse` é pura e testável;
`download` é um wrapper fino com fetcher injetável.

Saída normalizada (DataFrame plano que já alimenta services/backtest):
    date, league, season, home, away, home_goals, away_goals,
    o_home, o_draw, o_away,   # odds decimais de ABERTURA
    c_home, c_draw, c_away    # odds decimais de FECHAMENTO (fonte de verdade do CLV)
Quando a camada de persistência existir (Fase 1+), este frame vira linhas de
Match (placar/liga/temporada) + Odds (abertura/fechamento por mercado).
"""

from __future__ import annotations

import io
import urllib.request
from collections.abc import Callable

import pandas as pd

BASE_URL = "https://www.football-data.co.uk/mmz4281"

_CORE = ("Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG")

# Preferência de book para 1X2: B365 → Pinnacle → média do mercado.
_OPENING = (
    ("B365H", "B365D", "B365A"),
    ("PSH", "PSD", "PSA"),
    ("AvgH", "AvgD", "AvgA"),
)
_CLOSING = (
    ("B365CH", "B365CD", "B365CA"),
    ("PSCH", "PSCD", "PSCA"),
    ("AvgCH", "AvgCD", "AvgCA"),
)


def season_url(fd_code: str, season: str) -> str:
    """URL do CSV da liga/temporada (season no formato football-data, ex.: '2324')."""
    return f"{BASE_URL}/{season}/{fd_code}.csv"


def parse(raw: pd.DataFrame, league: str, season: str) -> pd.DataFrame:
    """Normaliza o CSV cru do football-data para o schema Match/Odds.

    Descarta jogos não disputados (sem placar). Levanta ValueError se faltarem
    colunas essenciais ou não houver nenhuma tripla de odds 1X2.
    """
    missing = [c for c in _CORE if c not in raw.columns]
    if missing:
        raise ValueError(f"colunas essenciais ausentes no CSV: {missing}")

    open_cols = _pick_triplet(raw, _OPENING)
    close_cols = _pick_triplet(raw, _CLOSING)
    if open_cols is None or close_cols is None:
        raise ValueError("CSV sem colunas de odds 1X2 (abertura e/ou fechamento)")

    df = raw.copy()
    # só jogos disputados (placar presente)
    df = df.dropna(subset=["FTHG", "FTAG"])

    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["Date"], dayfirst=True, errors="coerce"),
            "league": league,
            "season": season,
            "home": df["HomeTeam"].astype("string").str.strip(),
            "away": df["AwayTeam"].astype("string").str.strip(),
            "home_goals": df["FTHG"].astype(int),
            "away_goals": df["FTAG"].astype(int),
        }
    )
    for sel, oc, cc in zip(
        ("home", "draw", "away"), open_cols, close_cols, strict=True
    ):
        out[f"o_{sel}"] = pd.to_numeric(df[oc], errors="coerce").to_numpy()
        out[f"c_{sel}"] = pd.to_numeric(df[cc], errors="coerce").to_numpy()

    return out.reset_index(drop=True)


def download(
    fd_code: str, season: str, fetcher: Callable[[str], bytes] | None = None
) -> pd.DataFrame:
    """Baixa o CSV cru da liga/temporada. `fetcher` injetável para testes."""
    fetch = fetcher or _http_get
    payload = fetch(season_url(fd_code, season))
    return pd.read_csv(io.BytesIO(payload), encoding="latin-1")


def load(
    league: str,
    season: str,
    fd_code: str | None = None,
    fetcher: Callable[[str], bytes] | None = None,
) -> pd.DataFrame:
    """download + parse → Match/Odds normalizado de uma liga/temporada."""
    raw = download(fd_code or league, season, fetcher=fetcher)
    return parse(raw, league=league, season=season)


def _pick_triplet(df: pd.DataFrame, candidates) -> tuple[str, str, str] | None:
    """Primeira tripla (H, D, A) totalmente presente no DataFrame."""
    for triplet in candidates:
        if all(c in df.columns for c in triplet):
            return triplet
    return None


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "value-lab/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (URL fixa do projeto)
        return resp.read()
