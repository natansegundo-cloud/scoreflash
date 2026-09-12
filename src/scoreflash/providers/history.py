"""Provedor de histórico sob demanda para consultas de estatísticas."""

from __future__ import annotations

from collections.abc import Sequence

from ..models import Match, Team, Venue
from .flashscore import FlashscoreClient


class FlashscoreHistoryProvider:
    """Busca o histórico e baixa estatísticas apenas para os jogos selecionados."""

    def __init__(
        self,
        client: FlashscoreClient,
        *,
        team_slug: str,
        country_id: int | None = None,
        results_page: int = 1,
    ) -> None:
        self._client = client
        self._team_slug = team_slug
        self._country_id = country_id
        self._results_page = results_page

    def recent_matches(self, team: Team, limit: int) -> Sequence[Match]:
        return self.recent_matches_for_venue(team, limit, Venue.ANY)

    def recent_matches_for_venue(
        self,
        team: Team,
        limit: int,
        venue: Venue,
    ) -> Sequence[Match]:
        if limit <= 0:
            raise ValueError("limit deve ser maior que zero.")
        initial_results = self._client.fetch_initial_participant_results(
            team.external_id,
            self._team_slug,
        )
        candidates = list(initial_results.matches)
        available = [
            match
            for match in candidates
            if match.finished
            and team.external_id in {match.home_team.external_id, match.away_team.external_id}
            and (venue is Venue.ANY or match.venue_for(team) is venue)
        ]
        if self._country_id is not None and len(available) < limit:
            historical_results = self._client.fetch_participant_results(
                team.external_id,
                self._country_id,
                page=self._results_page,
            )
            known_event_ids = {match.external_id for match in candidates}
            candidates.extend(
                match
                for match in historical_results.matches
                if match.external_id not in known_event_ids
            )
        selected = sorted(
            (
                match
                for match in candidates
                if match.finished
                and team.external_id
                in {match.home_team.external_id, match.away_team.external_id}
                and (venue is Venue.ANY or match.venue_for(team) is venue)
            ),
            key=lambda match: match.kickoff,
            reverse=True,
        )[:limit]
        return tuple(self._client.hydrate_match_statistics(match) for match in selected)
