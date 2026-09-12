"""Orquestra pergunta, time local, dados ao vivo e resposta final."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ..config import Settings
from ..errors import (
    LLMUnavailableError,
    QuestionInterpretationError,
    TeamConfigurationError,
    TeamNotFoundError,
)
from ..llm.groq import GroqQuestionInterpreter, QuestionIntent
from ..models import Match, StatisticQuery, Team, Venue
from ..normalization import normalize_text
from ..providers.api_football import ApiFootballPlayerStatisticsClient
from ..providers.flashscore import FlashscoreClient
from ..providers.history import FlashscoreHistoryProvider
from ..storage.sqlite import QueryCache, TeamIndex
from .discovery import TeamDiscoveryService
from .insights import build_team_insight, confidence_for_sample
from .narration import narrate_average
from .player_opportunities import PlayerOpportunityResult, PlayerOpportunityService
from .statistics import calculate_average, metric_key


class QuestionInterpreter(Protocol):
    def parse(self, question: str, known_teams: Sequence[str]) -> QuestionIntent: ...


class RuleBasedQuestionInterpreter:
    _GAMES_RE = re.compile(r"(?:ultimos|ultimas)\s+(\d+)\s+jogos?", re.IGNORECASE)
    _METRICS = (
        ("finaliza", "finalizações"),
        ("chute", "chutes"),
        ("escante", "escanteios"),
        ("posse", "posse de bola"),
        ("cartao amarelo", "cartões amarelos"),
        ("faltas", "faltas"),
    )
    _COMPETITIONS = (
        "premier league",
        "champions league",
        "copa libertadores",
        "copa sul americana",
        "brasileirao",
        "la liga",
        "serie a",
        "bundesliga",
        "ligue 1",
    )

    def parse(self, question: str, known_teams: Sequence[str]) -> QuestionIntent:
        lowered = question.casefold()
        normalized_question = normalize_text(question)
        compact_question = normalized_question.replace(" ", "")
        team_name = next(
            (
                team
                for team in known_teams
                if (candidate := normalize_text(team))
                and (
                    f" {candidate} " in f" {normalized_question} "
                    or candidate.replace(" ", "") in compact_question
                )
            ),
            "",
        )
        metric = next((value for hint, value in self._METRICS if hint in lowered), "")
        games_match = self._GAMES_RE.search(lowered)
        games = int(games_match.group(1)) if games_match else 5
        venue = (
            Venue.HOME
            if "em casa" in lowered or "mandante" in lowered
            else Venue.AWAY
            if "fora de casa" in lowered or "visitante" in lowered
            else Venue.ANY
        )
        competition_name = next(
            (competition for competition in self._COMPETITIONS if competition in normalized_question),
            "",
        )
        if not metric:
            raise QuestionInterpretationError(
                "Ainda preciso reconhecer o time e a estatística. "
                "Tente algo como: média de finalizações do Newell's nos últimos 5 jogos."
            )
        return QuestionIntent(
            team_name=team_name,
            metric=metric,
            games=games,
            venue=venue,
            competition_name=competition_name,
        )


@dataclass(frozen=True, slots=True)
class QueryResult:
    answer: str
    team: str
    metric: str
    games: int
    venue: str
    average: float
    unit: str
    matches: tuple[dict[str, object], ...]
    # Valor opcional para manter compatibilidade com respostas que ficaram no
    # cache antes de a competição passar a fazer parte do recorte.
    competition: str | None = None
    cached: bool = False
    insight: str = ""
    confidence: str = "inicial"
    kind: str = "team_statistic"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class QueryService:
    def __init__(
        self,
        settings: Settings,
        teams: TeamIndex,
        cache: QueryCache,
        discovery: TeamDiscoveryService | None = None,
        player_opportunities: PlayerOpportunityService | None = None,
    ) -> None:
        self._settings = settings
        self._teams = teams
        self._cache = cache
        self._discovery = discovery or TeamDiscoveryService(teams)
        self._player_opportunities = player_opportunities or PlayerOpportunityService(
            individual_statistics=(
                ApiFootballPlayerStatisticsClient(settings.api_football_api_key)
                if settings.api_football_api_key
                else None
            )
        )
        self._fallback_interpreter = RuleBasedQuestionInterpreter()
        self._interpreter: QuestionInterpreter = (
            GroqQuestionInterpreter(settings.groq_api_key, settings.groq_model or "llama-3.3-70b-versatile")
            if settings.groq_api_key
            else self._fallback_interpreter
        )

    def execute(self, question: str) -> QueryResult | PlayerOpportunityResult:
        if self._is_player_opportunity_question(question):
            team = self._resolve_team(question, "")
            cache_key = "|".join(("player-opportunity", team.external_id, normalize_text(question)))
            cached = self._cache.get(cache_key)
            if cached is not None:
                return PlayerOpportunityResult(**cached)
            result = self._player_opportunities.evaluate(question, team)
            self._cache.put(cache_key, result.as_dict(), timedelta(hours=4))
            return result

        aliases = self._teams.aliases("flashscore")
        try:
            intent = self._interpreter.parse(question, aliases)
        except LLMUnavailableError:
            intent = self._fallback_interpreter.parse(question, aliases)
        team = self._resolve_team(question, intent.team_name)
        if not team.participant_slug:
            raise TeamConfigurationError(f"Ainda não há slug de busca para {team.name}.")

        cache_key = "|".join(
            (
                team.external_id,
                metric_key(intent.metric),
                str(intent.games),
                intent.venue.value,
                normalize_text(intent.competition_name),
            )
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return QueryResult(**{**cached, "cached": True})

        client = FlashscoreClient(self._settings.flashscore_signature)
        history = FlashscoreHistoryProvider(
            client,
            team_slug=team.participant_slug,
            country_id=team.country_id,
        )
        matches = history.recent_matches_for_venue(team, intent.games, intent.venue)
        statistic = calculate_average(
            StatisticQuery(
                team=team,
                metric=intent.metric,
                games=intent.games,
                venue=intent.venue,
                competition_name=intent.competition_name or None,
            ),
            matches,
        )
        result = QueryResult(
            answer=narrate_average(statistic),
            team=team.name,
            metric=intent.metric,
            games=len(statistic.matches_used),
            venue=intent.venue.value,
            competition=intent.competition_name or None,
            average=statistic.average,
            unit=statistic.unit.value,
            matches=tuple(self._serialize_match(match) for match in statistic.matches_used),
            insight=build_team_insight(statistic),
            confidence=confidence_for_sample(len(statistic.matches_used)),
        )
        self._cache.put(cache_key, result.as_dict(), timedelta(minutes=8))
        return result

    @staticmethod
    def _is_player_opportunity_question(question: str) -> bool:
        normalized = normalize_text(question)
        asks_for_market = any(
            marker in normalized
            for marker in ("finaliza", "chute", "falta", "cartao")
        )
        asks_for_recommendation = any(
            marker in normalized
            for marker in ("boa ideia", "vale", "recomenda", "prop", "aposta")
        )
        return asks_for_market and asks_for_recommendation

    _is_player_finalization_question = _is_player_opportunity_question

    def close(self) -> None:
        self._teams.close()
        self._cache.close()

    def configure_api_football(self, api_key: str) -> None:
        """Ativa a fonte individual na instância local, sem reiniciar a tela."""
        self._player_opportunities = PlayerOpportunityService(
            individual_statistics=ApiFootballPlayerStatisticsClient(api_key)
        )

    def _resolve_team(self, question: str, hinted_name: str) -> Team:
        if hinted_name:
            try:
                return self._teams.resolve("flashscore", hinted_name)
            except TeamNotFoundError:
                pass
        try:
            return self._teams.resolve_mentioned("flashscore", question)
        except TeamNotFoundError:
            return self._discovery.resolve(question, hinted_name)

    @staticmethod
    def _serialize_match(match: Match) -> dict[str, object]:
        goals = match.statistics.get("goals")
        return {
            "id": match.external_id,
            "date": match.kickoff.astimezone(UTC).date().isoformat(),
            "home_team": match.home_team.name,
            "away_team": match.away_team.name,
            "score": list(goals) if goals else None,
            "competition": match.competition_name,
        }
