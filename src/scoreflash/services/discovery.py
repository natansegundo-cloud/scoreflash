"""Resolução de equipes que ainda não existem no índice local."""

from __future__ import annotations

from typing import Protocol

from ..errors import TeamNotFoundError
from ..models import Team
from ..normalization import normalize_text
from ..providers.search import FlashscoreSearchClient, SearchTeam
from ..storage.sqlite import TeamIndex


class TeamSearchProvider(Protocol):
    def search_teams(self, query: str, *, limit: int = 10) -> tuple[SearchTeam, ...]: ...


class TeamDiscoveryService:
    """Procura uma equipe, valida o nome no texto e a memoriza localmente."""

    _IGNORED_WORDS = frozenset(
        {
            "a",
            "ao",
            "aos",
            "boa",
            "casa",
            "com",
            "da",
            "das",
            "de",
            "do",
            "dos",
            "em",
            "e",
            "finalizacao",
            "finalizacoes",
            "fora",
            "ideia",
            "jogos",
            "media",
            "nos",
            "no",
            "o",
            "os",
            "para",
            "partida",
            "qual",
            "quem",
            "tem",
            "ultimas",
            "ultimos",
        }
    )

    def __init__(self, index: TeamIndex, search: TeamSearchProvider | None = None) -> None:
        self._index = index
        self._search = search or FlashscoreSearchClient()

    def resolve(self, question: str, hinted_name: str = "") -> Team:
        for candidate in self._candidate_queries(question, hinted_name):
            for result in self._search.search_teams(candidate):
                if not self._is_mentioned(result, question, hinted_name):
                    continue
                team = Team(
                    provider="flashscore",
                    external_id=result.external_id,
                    name=result.name,
                    country=result.country,
                    participant_slug=result.slug,
                    country_id=result.country_id,
                )
                self._index.upsert(team, aliases=(candidate,))
                return team
        raise TeamNotFoundError(
            "Não consegui identificar a equipe. Tente escrever o nome completo, "
            "como: média de finalizações do Flamengo nos últimos 5 jogos."
        )

    def _candidate_queries(self, question: str, hinted_name: str) -> tuple[str, ...]:
        normalized_hint = normalize_text(hinted_name)
        if normalized_hint:
            return (normalized_hint,)
        words = [
            word
            for word in normalize_text(question).split()
            if len(word) >= 3 and word not in self._IGNORED_WORDS and not word.isdigit()
        ]
        candidates: list[str] = []
        for width in range(min(4, len(words)), 0, -1):
            for start in range(len(words) - width + 1):
                candidate = " ".join(words[start : start + width])
                if candidate not in candidates:
                    candidates.append(candidate)
        return tuple(candidates[:20])

    @staticmethod
    def _is_mentioned(result: SearchTeam, question: str, hinted_name: str) -> bool:
        target = normalize_text(hinted_name or question)
        team_name = normalize_text(result.name)
        return f" {team_name} " in f" {target} "
