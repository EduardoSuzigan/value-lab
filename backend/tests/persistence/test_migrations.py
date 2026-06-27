"""Guarda de drift: a migration Alembic tem de bater com os models.

Os outros testes montam o schema via `create_all`, então a migration nunca é
exercitada. Sem isto, mudar um model sem gerar a migration passaria no CI e só
divergiria em produção (Neon). Aqui rodamos `alembic upgrade head` num SQLite
limpo e exigimos zero diff estrutural vs `Base.metadata`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.models import Base

_BACKEND = Path(__file__).resolve().parents[2]
_STRUCTURAL = {"add_table", "remove_table", "add_column", "remove_column"}


def test_migrations_match_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'drift.db'}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        diffs = compare_metadata(ctx, Base.metadata)

    structural = [d for d in diffs if isinstance(d, tuple) and d[0] in _STRUCTURAL]
    assert not structural, f"migration fora de sync com os models: {structural}"
