"""Modelos de domínio independentes da fonte de dados."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Mapping


class Venue(StrEnum):
    ANY = "any"
    HOME = "home"
    AWAY = "away"


class StatisticUnit(StrEnum):
    NUMBER = "number"
    PERCENTAGE = "percentage"


@dataclass(frozen=True, slots=True)
class Team:
    provider: str
    external_id: str
    name: str
    country: str | None = None
    participant_slug: str | None = None
    country_id: int | None = None


@dataclass(frozen=True, slots=True)
class Player:
    """Identidade de um atleta encontrada na busca da fonte de dados."""

    provider: str
    external_id: str
    name: str
    participant_slug: str
    position: str | None = None
    country: str | None = None
    team_external_id: str | None = None
    team_name: str | None = None


@dataclass(frozen=True, slots=True)
class Match:
    external_id: str
    kickoff: datetime
    home_team: Team
    away_team: Team
    finished: bool
    # Chave: métrica normalizada. Valor: (mandante, visitante).
    statistics: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    statistic_units: Mapping[str, StatisticUnit] = field(default_factory=dict)
    competition_name: str | None = None

    def team_value(self, team: Team, metric: str) -> float | None:
        values = self.statistics.get(metric)
        if values is None:
            return None
        if team.external_id == self.home_team.external_id:
            return values[0]
        if team.external_id == self.away_team.external_id:
            return values[1]
        return None

    def venue_for(self, team: Team) -> Venue | None:
        if team.external_id == self.home_team.external_id:
            return Venue.HOME
        if team.external_id == self.away_team.external_id:
            return Venue.AWAY
        return None

    def statistic_unit(self, metric: str) -> StatisticUnit:
        return self.statistic_units.get(metric, StatisticUnit.NUMBER)


@dataclass(frozen=True, slots=True)
class StatisticQuery:
    team: Team
    metric: str
    games: int
    venue: Venue = Venue.ANY
    competition_name: str | None = None


@dataclass(frozen=True, slots=True)
class StatisticResult:
    query: StatisticQuery
    average: float
    matches_used: tuple[Match, ...]
    unit: StatisticUnit = StatisticUnit.NUMBER
