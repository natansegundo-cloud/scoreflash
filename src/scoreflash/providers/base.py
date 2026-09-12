"""Contratos de provedores; a regra de negócio não conhece HTTP nem feeds."""

from __future__ import annotations

from typing import Protocol, Sequence

from ..models import Match, Team


class MatchHistoryProvider(Protocol):
    def recent_matches(self, team: Team, limit: int) -> Sequence[Match]:
        """Retorna partidas mais recentes, preferencialmente em ordem decrescente."""
