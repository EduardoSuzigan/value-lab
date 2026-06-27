"""worker.run.run_pipeline: orquestra ETL → train por liga, sem HTTP.

Entrypoint batch (`python -m worker.run`). Aqui testamos o núcleo orquestrador
com um fetcher injetável (sem rede): baixa CSV football-data → upsert Match/Odds
→ train por (liga, temporada). Liga com poucos jogos é pulada no treino mas seus
Match/Odds são persistidos mesmo assim.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.models import Match, ModelRun, Prediction
from worker.run import run_pipeline

_TEAMS = ("A", "B", "C", "D")
_HG = [2, 1, 0, 3, 1, 2, 1, 0, 2, 1, 3, 0]
_AG = [1, 1, 2, 0, 1, 0, 2, 1, 1, 2, 0, 1]
_SAMPLE = Path(__file__).parents[1] / "etl" / "fixtures" / "e0_sample.csv"


def _fd_csv_bytes() -> bytes:
    """CSV no formato football-data com 12 jogos (round-robin de 4 times)."""
    pairs = [(h, a) for h in _TEAMS for a in _TEAMS if h != a]
    rows = []
    for i, (h, a) in enumerate(pairs):
        rows.append(
            {
                "Date": f"{i + 1:02d}/01/2024",
                "HomeTeam": h, "AwayTeam": a,
                "FTHG": _HG[i], "FTAG": _AG[i],
                "B365H": 2.0, "B365D": 3.3, "B365A": 3.8,
                "B365CH": 1.95, "B365CD": 3.4, "B365CA": 4.0,
            }
        )
    return pd.DataFrame(rows).to_csv(index=False).encode("latin-1")


def test_pipeline_etl_then_train(session):
    summary = run_pipeline(
        session, seasons=["2324"], codes=["E0"],
        fetcher=lambda _url: _fd_csv_bytes(),
    )

    assert session.query(Match).count() == 12
    assert session.query(ModelRun).count() == 1
    assert session.query(Prediction).count() == 12 * 7
    assert summary[("E0", "2324")]["matches"] == 12
    assert summary[("E0", "2324")]["run_id"] is not None


def test_pipeline_persists_but_skips_train_when_too_few_matches(session):
    sample = _SAMPLE.read_bytes()
    summary = run_pipeline(
        session, seasons=["2324"], codes=["E0"], fetcher=lambda _url: sample,
    )

    assert session.query(Match).count() > 0  # Match/Odds persistidos
    assert session.query(ModelRun).count() == 0  # treino pulado
    assert summary[("E0", "2324")]["run_id"] is None
    assert "skipped" in summary[("E0", "2324")]
