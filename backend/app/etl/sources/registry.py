"""Registro de fontes por liga.

Cada liga aponta para sua fonte de dados (football-data.co.uk no MVP). Adicionar
uma liga = registrar aqui (ver .claude/skills/add-league). O fit é por liga; este
registro NÃO mistura ligas — só descreve de onde vêm os dados de cada uma.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueSource:
    code: str          # código canônico do projeto (= código football-data no MVP)
    name: str
    country: str
    fd_code: str       # código no football-data.co.uk (ex.: E0, SP1, D1, BRA)
    experimental: bool = False


# MVP: 5 europeias sólidas + Brasil. Saudi (SAU) entra como experimental na Fase 1+.
_LEAGUES: dict[str, LeagueSource] = {
    "E0": LeagueSource("E0", "Premier League", "England", "E0"),
    "SP1": LeagueSource("SP1", "La Liga", "Spain", "SP1"),
    "D1": LeagueSource("D1", "Bundesliga", "Germany", "D1"),
    "I1": LeagueSource("I1", "Serie A", "Italy", "I1"),
    "F1": LeagueSource("F1", "Ligue 1", "France", "F1"),
    "BRA": LeagueSource("BRA", "Brasileirão Série A", "Brazil", "BRA"),
}


def get_source(code: str) -> LeagueSource:
    """Fonte registrada da liga `code`. Levanta KeyError se desconhecida."""
    return _LEAGUES[code]


def codes() -> list[str]:
    """Códigos de liga registrados."""
    return list(_LEAGUES)
