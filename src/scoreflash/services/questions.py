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
    PlayerNotFoundError,
    ProviderAccessError,
    QuestionInterpretationError,
    TeamConfigurationError,
    TeamNotFoundError,
)
from ..llm.groq import GroqQuestionInterpreter, QuestionIntent
from ..models import Match, StatisticQuery, Team, Venue
from ..normalization import normalize_text
from ..providers.api_football import (
    ApiFootballHeadToHeadClient,
    ApiFootballHeadToHeadHistory,
    ApiFootballPlayerStatisticsClient,
)
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


class HeadToHeadProvider(Protocol):
    def recent_matches(
        self,
        team_name: str,
        opponent_name: str,
        *,
        games: int,
        competition_name: str = "",
    ) -> ApiFootballHeadToHeadHistory: ...


class RuleBasedQuestionInterpreter:
    _GAMES_RE = re.compile(r"(?:ultimos|ultimas)\s+(\d+)\s+jogos?", re.IGNORECASE)
    _HEAD_TO_HEAD_RE = re.compile(
        r"(?:confronto(?:s)?(?:\s+direto(?:s)?)?(?:\s+entre)?|entre)\s+"
        r"(?P<team>[a-z0-9 .'-]+?)\s+(?:e|x|vs\.?|contra)\s+"
        r"(?P<opponent>[a-z0-9 .'-]+?)(?=\s+(?:sendo|com|pelo|pela|nos|nas|em|fora|onde)\b|[?.!,]|$)",
        re.IGNORECASE,
    )
    _METRICS = (
        ("gol", "gols"),
        ("finaliza", "finalizações"),
        ("chute", "chutes"),
        ("escante", "escanteios"),
        ("posse", "posse de bola"),
        ("cartao amarelo", "cartões amarelos"),
        ("faltas", "faltas"),
    )
    _COMPETITIONS = (
        ("campeonato brasileiro", "brasileirao"),
        ("brasileirao", "brasileirao"),
        ("premier league", "premier league"),
        ("champions league", "champions league"),
        ("copa libertadores", "copa libertadores"),
        ("copa sul americana", "copa sul americana"),
        ("la liga", "la liga"),
        ("serie a", "serie a"),
        ("bundesliga", "bundesliga"),
        ("ligue 1", "ligue 1"),
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
            (name for hint, name in self._COMPETITIONS if hint in normalized_question),
            "",
        )
        if not metric:
            raise QuestionInterpretationError(
                "Ainda preciso reconhecer o time e a estatística. "
                "Tente algo como: média de finalizações do Newell's nos últimos 5 jogos."
            )
        head_to_head = self._HEAD_TO_HEAD_RE.search(normalized_question)
        if head_to_head is not None:
            primary_team = head_to_head.group("team").strip()
            opponent_name = head_to_head.group("opponent").strip()
            named_venue = re.search(
                r"\bsendo\s+(?P<team>[a-z0-9 .'-]+?)\s+(?:o\s+)?(?:mandante|visitante)\b",
                normalized_question,
            )
            if (
                named_venue is not None
                and normalize_text(named_venue.group("team")) == normalize_text(opponent_name)
            ):
                primary_team, opponent_name = opponent_name, primary_team
            return QuestionIntent(
                team_name=primary_team,
                opponent_name=opponent_name,
                kind="head_to_head",
                metric=metric,
                games=games,
                venue=venue,
                competition_name=competition_name,
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


@dataclass(frozen=True, slots=True)
class HeadToHeadResult:
    answer: str
    team: str
    opponent: str
    metric: str
    games: int
    venue: str
    average: float
    team_average: float
    opponent_average: float
    matches: tuple[dict[str, object], ...]
    competition: str | None = None
    cached: bool = False
    insight: str = ""
    confidence: str = "inicial"
    kind: str = "head_to_head"

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
        head_to_head: HeadToHeadProvider | None = None,
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
        self._head_to_head = head_to_head or (
            ApiFootballHeadToHeadClient(settings.api_football_api_key)
            if settings.api_football_api_key
            else None
        )
        self._fallback_interpreter = RuleBasedQuestionInterpreter()
        self._interpreter: QuestionInterpreter = (
            GroqQuestionInterpreter(settings.groq_api_key, settings.groq_model or "llama-3.3-70b-versatile")
            if settings.groq_api_key
            else self._fallback_interpreter
        )

    def execute(self, question: str) -> QueryResult | HeadToHeadResult | PlayerOpportunityResult:
        if self._is_player_opportunity_question(question):
            try:
                team = self._resolve_team(question, "")
            except TeamNotFoundError:
                return self._execute_unscoped_player_statistic(question)
            cache_key = "|".join(("player-opportunity", team.external_id, normalize_text(question)))
            cached = self._cache.get(cache_key)
            if cached is not None:
                return PlayerOpportunityResult(**cached)
            result = self._player_opportunities.evaluate(question, team)
            self._cache.put(cache_key, result.as_dict(), timedelta(hours=4))
            return result

        aliases = self._teams.aliases("flashscore")
        try:
            direct_intent = self._fallback_interpreter.parse(question, aliases)
        except QuestionInterpretationError:
            direct_intent = None
        if direct_intent is not None and direct_intent.kind == "head_to_head":
            return self._execute_head_to_head(direct_intent)
        try:
            intent = self._interpreter.parse(question, aliases)
        except LLMUnavailableError:
            intent = self._fallback_interpreter.parse(question, aliases)
        if intent.kind == "head_to_head":
            return self._execute_head_to_head(intent)
        try:
            team = self._resolve_team(question, intent.team_name)
        except TeamNotFoundError as team_error:
            if self._is_player_statistic_question(question):
                try:
                    return self._execute_unscoped_player_statistic(question)
                except PlayerNotFoundError:
                    raise team_error
            raise
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

    def _execute_unscoped_player_statistic(self, question: str) -> PlayerOpportunityResult:
        cache_key = "|".join(("player-statistic-v2", normalize_text(question)))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return PlayerOpportunityResult(**cached)
        result = self._player_opportunities.evaluate_statistic(question)
        if result.status != "provider_unavailable":
            self._cache.put(cache_key, result.as_dict(), timedelta(hours=4))
        return result

    def _execute_head_to_head(self, intent: QuestionIntent) -> HeadToHeadResult:
        if metric_key(intent.metric) != "goals":
            raise QuestionInterpretationError(
                "No confronto direto, esta primeira versão calcula médias de gols."
            )
        if self._head_to_head is None:
            raise ProviderAccessError(
                "Configure API_FOOTBALL_API_KEY para consultar confrontos diretos."
            )
        cache_key = "|".join(
            (
                "head-to-head",
                normalize_text(intent.team_name),
                normalize_text(intent.opponent_name),
                str(intent.games),
                intent.venue.value,
                normalize_text(intent.competition_name),
            )
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return HeadToHeadResult(**{**cached, "cached": True})

        history = self._head_to_head.recent_matches(
            intent.team_name,
            intent.opponent_name,
            games=intent.games,
            competition_name=intent.competition_name,
        )
        statistic = calculate_average(
            StatisticQuery(
                team=history.team,
                metric="gols",
                games=intent.games,
                venue=intent.venue,
            ),
            history.matches,
        )
        matches_used = statistic.matches_used
        opponent_average = sum(
            match.team_value(history.opponent, "goals") or 0.0 for match in matches_used
        ) / len(matches_used)
        total_average = statistic.average + opponent_average
        observed_games = len(matches_used)
        venue = {
            Venue.HOME: f"com {history.team.name} mandante",
            Venue.AWAY: f"com {history.team.name} visitante",
            Venue.ANY: "em todos os mandos",
        }[intent.venue]
        competition = self._competition_label(intent.competition_name)
        available = " disponíveis" if observed_games != intent.games else ""
        answer = (
            f"Nos últimos {observed_games} confrontos{available} entre {history.team.name} e "
            f"{history.opponent.name}, {venue}{f' pelo {competition}' if competition else ''}, "
            f"{history.team.name} marcou média de {self._format_number(statistic.average)} gols, "
            f"{history.opponent.name} marcou {self._format_number(opponent_average)} e o total foi "
            f"{self._format_number(total_average)} gols por partida."
        )
        insight = (
            f"A conta usa {observed_games} confronto{'s' if observed_games != 1 else ''} encerrado"
            f"{'s' if observed_games != 1 else ''} {venue}. O total médio foi "
            f"{self._format_number(total_average)} gols por jogo. "
            f"Confiança {confidence_for_sample(observed_games)}."
        )
        result = HeadToHeadResult(
            answer=answer,
            team=history.team.name,
            opponent=history.opponent.name,
            metric="gols",
            games=observed_games,
            venue=intent.venue.value,
            competition=competition,
            average=total_average,
            team_average=statistic.average,
            opponent_average=opponent_average,
            matches=tuple(self._serialize_match(match) for match in matches_used),
            insight=insight,
            confidence=confidence_for_sample(observed_games),
        )
        self._cache.put(cache_key, result.as_dict(), timedelta(hours=12))
        return result

    @staticmethod
    def _competition_label(competition_name: str) -> str | None:
        if normalize_text(competition_name) in {"brasileirao", "campeonato brasileiro"}:
            return "Brasileirão"
        return competition_name or None

    @staticmethod
    def _format_number(value: float) -> str:
        return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")

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

    @staticmethod
    def _is_player_statistic_question(question: str) -> bool:
        normalized = normalize_text(question)
        asks_for_market = any(
            marker in normalized
            for marker in ("finaliza", "chute", "falta", "cartao")
        )
        has_player_verb = bool(
            re.search(r"\b(?:tem|possui|fez|acertou|registrou)\b", normalized)
        )
        has_named_subject = bool(
            re.search(r"\bde\s+[a-z]{3,}(?:\s+[a-z]{3,})+\b", normalized)
        )
        return asks_for_market and (has_player_verb or "jogador" in normalized or "atleta" in normalized or has_named_subject)

    def close(self) -> None:
        self._teams.close()
        self._cache.close()

    def configure_api_football(self, api_key: str) -> None:
        """Ativa a fonte individual na instância local, sem reiniciar a tela."""
        self._player_opportunities = PlayerOpportunityService(
            individual_statistics=ApiFootballPlayerStatisticsClient(api_key)
        )
        self._head_to_head = ApiFootballHeadToHeadClient(api_key)

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
