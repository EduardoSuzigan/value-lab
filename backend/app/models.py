"""Modelo de dados (SQLAlchemy 2.0, tipado).

Dimensões e fatos da Fase 1. Schema dialect-agnóstico: roda em SQLite (testes/boot
local) e Postgres/Neon (produção) sem mudança. Sem I/O aqui — só o mapeamento.

Invariantes (ver .claude/rules/predictions-append-only.md):
- `Match.home_goals/away_goals` None = jogo futuro (ainda não disputado).
- `ModelRun` é POR LIGA (fit por liga, nunca pooled — per-league-fit.md).
- `ModelRun`/`Prediction` são APPEND-ONLY: cada ajuste cria um novo run; predições
  nunca são sobrescritas e sempre referenciam seu `run_id`.
- `Odds` é a fonte de verdade do CLV (abertura/fechamento por seleção); o ETL
  escreve só `Match`/`Odds`, nunca `Prediction`/`ModelRun`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class League(Base):
    __tablename__ = "league"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(unique=True, index=True)  # = football-data
    name: Mapped[str]
    country: Mapped[str]
    experimental: Mapped[bool] = mapped_column(default=False)

    teams: Mapped[list[Team]] = relationship(back_populates="league")


class Team(Base):
    __tablename__ = "team"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("league.id"))
    name: Mapped[str]

    league: Mapped[League] = relationship(back_populates="teams")

    __table_args__ = (UniqueConstraint("league_id", "name"),)


class Match(Base):
    __tablename__ = "match"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("league.id"))
    season: Mapped[str]
    date: Mapped[datetime]
    home_team_id: Mapped[int] = mapped_column(ForeignKey("team.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("team.id"))
    home_goals: Mapped[int | None]  # None = jogo futuro
    away_goals: Mapped[int | None]

    league: Mapped[League] = relationship()
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])
    odds: Mapped[list[Odds]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )

    # Chave natural do fixture: num round-robin cada par ordenado (home, away)
    # joga 1x por temporada. `date` é atributo remarcável, não identidade.
    __table_args__ = (
        UniqueConstraint("league_id", "season", "home_team_id", "away_team_id"),
    )


class Odds(Base):
    __tablename__ = "odds"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("match.id"))
    market: Mapped[str]  # "1X2" | "OU25" | "BTTS"
    selection: Mapped[str]  # home/draw/away | over/under | yes/no
    open: Mapped[float | None]  # odd decimal de abertura
    close: Mapped[float | None]  # odd decimal de fechamento (fonte de verdade do CLV)

    match: Mapped[Match] = relationship(back_populates="odds")

    __table_args__ = (UniqueConstraint("match_id", "market", "selection"),)


class ModelRun(Base):
    __tablename__ = "model_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("league.id"))
    season: Mapped[str]
    xi: Mapped[float]  # decaimento temporal usado no fit
    # instante de auditoria (append-only) → TIMESTAMPTZ; o offset sobrevive no Neon
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    league: Mapped[League] = relationship()
    predictions: Mapped[list[Prediction]] = relationship(back_populates="run")


class Prediction(Base):
    __tablename__ = "prediction"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("model_run.id"))
    match_id: Mapped[int] = mapped_column(ForeignKey("match.id"))
    market: Mapped[str]  # "1X2" | "OU25" | "BTTS"
    selection: Mapped[str]  # home/draw/away | over/under | yes/no
    prob: Mapped[float]  # probabilidade do modelo (saída pura; EV derivado no read)

    run: Mapped[ModelRun] = relationship(back_populates="predictions")
    match: Mapped[Match] = relationship()

    __table_args__ = (
        UniqueConstraint("run_id", "match_id", "market", "selection"),
    )
