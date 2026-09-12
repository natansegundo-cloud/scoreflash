"""Descoberta segura de atletas citados em perguntas livres."""

from __future__ import annotations

from typing import Protocol

from ..errors import PlayerNotFoundError
from ..models import Player, Team
from ..normalization import normalize_text
from ..providers.search import FlashscoreSearchClient, SearchPlayer


class PlayerSearchProvider(Protocol):
    def search_players(self, query: str, *, limit: int = 10) -> tuple[SearchPlayer, ...]: ...


class PlayerDiscoveryService:
    """Localiza o jogador e confirma o clube antes de usar seus dados."""

    _IGNORED_WORDS = frozenset(
        {
            "a", "ao", "amanha", "boa", "casa", "com", "da", "das", "de", "do", "dos",
            "e", "eh", "em", "finalizar", "finalizacao", "finalizacoes", "fora", "ideia",
            "jogo", "jogos", "na", "no", "nos", "o", "os", "para", "pra", "prop", "uma", "vale",
        }
    )

    def __init__(self, search: PlayerSearchProvider | None = None) -> None:
        self._search = search or FlashscoreSearchClient()

    def resolve(self, question: str, team: Team) -> Player:
        normalized_question = normalize_text(question)
        for candidate in self._candidate_queries(normalized_question, team):
            for result in self._search.search_players(candidate):
                if not self._matches_question(result, normalized_question):
                    continue
                if not self._belongs_to_team(result, team):
                    continue
                return Player(
                    provider="flashscore",
                    external_id=result.external_id,
                    name=result.name,
                    participant_slug=result.slug,
                    position=result.position,
                    country=result.country,
                    team_external_id=result.team_external_id,
                    team_name=result.team_name,
                )
        raise PlayerNotFoundError(
            f"Não consegui confirmar o jogador citado no {team.name}. "
            "Tente escrever nome e sobrenome, por exemplo: Léo Ortiz no Flamengo."
        )

    def _candidate_queries(self, normalized_question: str, team: Team) -> tuple[str, ...]:
        team_words = set(normalize_text(team.name).split())
        words = [
            word for word in normalized_question.split()
            if len(word) >= 3 and word not in self._IGNORED_WORDS
            and word not in team_words and not word.isdigit()
        ]
        candidates: list[str] = []
        for width in range(min(4, len(words)), 0, -1):
            for start in range(len(words) - width + 1):
                candidate = " ".join(words[start : start + width])
                if candidate not in candidates:
                    candidates.append(candidate)
        return tuple(candidates[:15])

    @staticmethod
    def _matches_question(result: SearchPlayer, normalized_question: str) -> bool:
        name_words = normalize_text(result.name).split()
        return bool(name_words) and all(word in normalized_question.split() for word in name_words)

    @staticmethod
    def _belongs_to_team(result: SearchPlayer, team: Team) -> bool:
        if result.team_external_id and result.team_external_id == team.external_id:
            return True
        if result.team_name:
            return normalize_text(result.team_name) == normalize_text(team.name)
        return False
