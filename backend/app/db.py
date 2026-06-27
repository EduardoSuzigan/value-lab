"""Engine/session de persistência.

App/migrations apontam p/ `settings.database_url` (Neon em produção, Fase 2);
testes usam SQLite in-memory via `make_engine`. Sem lógica de domínio aqui.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


def make_engine(url: str) -> Engine:
    """Cria um Engine para `url`.

    SQLite in-memory usa StaticPool (uma única conexão compartilhada) para o
    schema sobreviver entre operações dentro do mesmo teste. Em SQLite as FKs
    só são checadas com `PRAGMA foreign_keys=ON` por conexão (Postgres já
    impõe nativamente).
    """
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)
