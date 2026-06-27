"""Entrypoint batch do pipeline: ETL → train por liga. Sem HTTP.

`python -m worker.run --seasons 2324 2223 [--leagues E0 SP1 ...]`

Substitui o antigo loop always-on: é chamável e termina (disparado pelo GitHub
Actions na Fase 2). Para cada (liga, temporada): baixa football-data → upsert
Match/Odds → treina Dixon-Coles (um ModelRun por liga). Ligas com poucos jogos
têm Match/Odds persistidos mas o treino é pulado.

A API nunca importa este módulo (batch pesado com scipy); ver CLAUDE.md.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.etl import football_data as fd
from app.etl.persist import upsert_matches
from app.etl.sources import registry
from app.services.train import train_league


def run_pipeline(
    session: Session,
    seasons: Iterable[str],
    codes: Iterable[str] | None = None,
    fetcher: Callable[[str], bytes] | None = None,
) -> dict[tuple[str, str], dict]:
    """ETL + treino p/ cada (liga, temporada). Retorna sumário por par."""
    codes = list(codes) if codes is not None else registry.codes()
    seasons = list(seasons)
    summary: dict[tuple[str, str], dict] = {}

    for code in codes:
        src = registry.get_source(code)
        for season in seasons:
            if src.feed == "new":  # feed único (Brasil): só fechamento, sem CLV
                df = fd.load_new(code, season, fd_code=src.fd_code, fetcher=fetcher)
            else:
                df = fd.load(code, season, fd_code=src.fd_code, fetcher=fetcher)
            upsert_matches(session, df)
            entry: dict = {"matches": len(df), "run_id": None}
            try:
                run = train_league(session, code, season)
                entry["run_id"] = run.id
            except ValueError as exc:  # poucos jogos p/ treinar
                entry["skipped"] = str(exc)
            summary[(code, season)] = entry
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="value-lab batch: ETL + treino")
    parser.add_argument("--seasons", nargs="+", required=True, help="ex.: 2324 2223")
    parser.add_argument(
        "--leagues", nargs="*", default=None, help="códigos (default: todas)"
    )
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        summary = run_pipeline(session, seasons=args.seasons, codes=args.leagues)

    for (code, season), entry in summary.items():
        status = f"run {entry['run_id']}" if entry["run_id"] else entry.get(
            "skipped", "skip"
        )
        print(f"{code} {season}: {entry['matches']} jogos → {status}")


if __name__ == "__main__":
    main()
