"""Dados determinísticos para desenvolvimento sem depender de uma fonte externa."""

from __future__ import annotations

from collections.abc import Sequence

from ..models import Match, Team


class InMemoryMatchProvider:
    def __init__(self, matches: Sequence[Match]) -> None:
        self._matches = tuple(matches)

    def recent_matches(self, team: Team, limit: int) -> Sequence[Match]:
        related = (
            match
            for match in self._matches
            if team.external_id in {match.home_team.external_id, match.away_team.external_id}
        )
        return tuple(sorted(related, key=lambda match: match.kickoff, reverse=True)[:limit])
