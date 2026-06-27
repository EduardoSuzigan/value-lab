"""Fixtures compartilhadas dos testes.

`session`: engine SQLite in-memory hermético por teste (offline, roda no sandbox).
App/migrations apontam p/ Neon; o schema é dialect-agnóstico. FK enforcement
ligado via db.make_engine.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app import db
from app.models import Base


@pytest.fixture
def session() -> Session:
    engine = db.make_engine("sqlite://")  # in-memory, conexão única (StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
