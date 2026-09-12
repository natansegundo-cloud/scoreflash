"""Catálogo inicial; a descoberta global será adicionada sobre esta mesma tabela."""

from __future__ import annotations

from .models import Team
from .storage.sqlite import TeamIndex


_INITIAL_TEAMS = (
    (
        Team(
            provider="flashscore",
            external_id="6gMiRHVj",
            name="Newell's Old Boys",
            country="Argentina",
            participant_slug="newells-old-boys",
            country_id=22,
        ),
        ("Newells", "Newell's", "Newell", "NOB"),
    ),
)


def seed_initial_catalog(index: TeamIndex) -> None:
    for team, aliases in _INITIAL_TEAMS:
        index.upsert(team, aliases)
