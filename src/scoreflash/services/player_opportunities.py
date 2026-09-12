"""Leitura conservadora de oportunidade de jogador.

Esta camada separa disponibilidade (presenças, minutos e rating) de produção.
Uma prop de finalização só recebe recomendação quando houver estatísticas
individuais verificadas para ela.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC
from math import floor
from statistics import mean
from typing import Protocol

from ..errors import ProviderAccessError
from ..models import Match, Player, Team
from ..normalization import normalize_text
from ..providers.api_football import (
    ApiFootballPlayerStatisticsClient,
    VerifiedPlayerMatchStatistics,
)
from ..providers.flashscore import FlashscoreClient
from ..providers.player import FlashscorePlayerClient, PlayerAppearance, PlayerProfile
from .player_discovery import PlayerDiscoveryService


class PlayerProfileProvider(Protocol):
    def fetch_profile(self, player: Player) -> PlayerProfile: ...


class TeamFixtureProvider(Protocol):
    def fetch_initial_participant_fixtures(
        self,
        participant_id: str,
        participant_slug: str,
    ) -> object: ...


class IndividualStatisticsProvider(Protocol):
    def recent_statistics(
        self,
        player_name: str,
        team_name: str | None = None,
        *,
        games: int = 5,
    ) -> tuple[VerifiedPlayerMatchStatistics, ...]: ...


@dataclass(frozen=True, slots=True)
class PlayerMarket:
    key: str
    label: str
    singular_label: str


_MARKETS = (
    PlayerMarket("shots_on_target", "chutes no alvo", "chute no alvo"),
    PlayerMarket("fouls_committed", "faltas cometidas", "falta cometida"),
    PlayerMarket("yellow_cards", "cartões amarelos", "cartão amarelo"),
    PlayerMarket("shots_total", "finalizações", "finalização"),
)


@dataclass(frozen=True, slots=True)
class PlayerOpportunityResult:
    kind: str
    answer: str
    player: str
    team: str
    market: str
    status: str
    recommendation: str
    threshold: int
    average_metric: float | None
    hit_rate: float | None
    appearances_considered: int
    average_minutes: float | None
    average_rating: float | None
    next_match: dict[str, object] | None
    appearances: tuple[dict[str, object], ...]
    individual_matches: tuple[dict[str, object], ...]
    insight: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class PlayerOpportunityService:
    """Monta o retrato atual do atleta para uma pergunta de prop."""

    def __init__(
        self,
        discovery: PlayerDiscoveryService | None = None,
        profiles: PlayerProfileProvider | None = None,
        fixtures: TeamFixtureProvider | None = None,
        individual_statistics: IndividualStatisticsProvider | None = None,
    ) -> None:
        self._discovery = discovery or PlayerDiscoveryService()
        self._profiles = profiles or FlashscorePlayerClient()
        self._fixtures = fixtures or FlashscoreClient()
        self._individual_statistics = individual_statistics

    def evaluate(self, question: str, team: Team) -> PlayerOpportunityResult:
        player = self._discovery.resolve(question, team)
        profile = self._profiles.fetch_profile(player)
        appearances = profile.appearances[:10]
        played = tuple(item for item in appearances if item.minutes is not None and item.minutes > 0)
        ratings = tuple(item.rating for item in played if item.rating is not None)
        next_match = self._next_match(team)
        average_minutes = round(mean(item.minutes for item in played), 1) if played else None
        average_rating = round(mean(ratings), 2) if ratings else None
        market = self._market_for_question(question)
        threshold = self._threshold_for_question(question)
        verified = self._verified_statistics(player, team)
        if isinstance(verified, tuple):
            opportunity = self._evaluate_verified(market, threshold, verified, average_minutes)
            if opportunity is not None:
                recommendation, average_metric, hit_rate, answer, insight = opportunity
                return PlayerOpportunityResult(
                    kind="player_opportunity",
                    answer=answer,
                    player=player.name,
                    team=team.name,
                    market=market.label,
                    status="ready",
                    recommendation=recommendation,
                    threshold=threshold,
                    average_metric=average_metric,
                    hit_rate=hit_rate,
                    appearances_considered=len(appearances),
                    average_minutes=average_minutes,
                    average_rating=average_rating,
                    next_match=next_match,
                    appearances=tuple(self._serialize_appearance(item) for item in appearances),
                    individual_matches=tuple(self._serialize_verified_match(item) for item in verified),
                    insight=insight,
                )

        status = "needs_provider_key" if verified is None else "insufficient_coverage"
        if isinstance(verified, ProviderAccessError):
            status = "provider_unavailable"
        answer, insight = self._narrate(
            player,
            team,
            appearances,
            played,
            average_minutes,
            average_rating,
            next_match,
            market,
            status,
        )
        return PlayerOpportunityResult(
            kind="player_opportunity",
            answer=answer,
            player=player.name,
            team=team.name,
            market=market.label,
            status=status,
            recommendation="sem dados",
            threshold=threshold,
            average_metric=None,
            hit_rate=None,
            appearances_considered=len(appearances),
            average_minutes=average_minutes,
            average_rating=average_rating,
            next_match=next_match,
            appearances=tuple(self._serialize_appearance(item) for item in appearances),
            individual_matches=(),
            insight=insight,
        )

    def evaluate_finalization(self, question: str, team: Team) -> PlayerOpportunityResult:
        """Compatibilidade temporária com a etapa inicial de finalizações."""
        return self.evaluate(question, team)

    def evaluate_statistic(self, question: str) -> PlayerOpportunityResult:
        """Responde uma média individual quando o clube não foi informado."""
        player = self._discovery.resolve_without_team(question)
        market = self._market_for_question(question)
        team_name = player.team_name or "equipe atual"
        verified = self._verified_statistics(player, team_name=player.team_name)
        if isinstance(verified, tuple):
            return self._build_statistic_result(player, team_name, market, verified)

        status = "needs_provider_key" if verified is None else "provider_unavailable"
        reason = (
            "Configure a API-Football para consultar as estatísticas individuais verificadas."
            if verified is None
            else str(verified)
        )
        return PlayerOpportunityResult(
            kind="player_opportunity",
            answer=f"Ainda não consegui calcular a média de {market.label} de {player.name}.",
            player=player.name,
            team=team_name,
            market=market.label,
            status=status,
            recommendation="sem dados",
            threshold=1,
            average_metric=None,
            hit_rate=None,
            appearances_considered=0,
            average_minutes=None,
            average_rating=None,
            next_match=None,
            appearances=(),
            individual_matches=(),
            insight=reason,
        )

    def _next_match(self, team: Team) -> dict[str, object] | None:
        if not team.participant_slug:
            return None
        retrieved = self._fixtures.fetch_initial_participant_fixtures(
            team.external_id,
            team.participant_slug,
        )
        matches = getattr(retrieved, "matches", ())
        future_matches = sorted(
            (match for match in matches if isinstance(match, Match) and not match.finished),
            key=lambda match: match.kickoff,
        )
        if not future_matches:
            return None
        match = future_matches[0]
        return {
            "id": match.external_id,
            "date": match.kickoff.astimezone(UTC).date().isoformat(),
            "home_team": match.home_team.name,
            "away_team": match.away_team.name,
            "competition": match.competition_name,
        }

    def _verified_statistics(
        self,
        player: Player,
        team: Team | None = None,
        team_name: str | None = None,
    ) -> tuple[VerifiedPlayerMatchStatistics, ...] | ProviderAccessError | None:
        if self._individual_statistics is None:
            return None
        try:
            return self._individual_statistics.recent_statistics(
                player.name,
                team.name if team is not None else team_name,
                games=5,
            )
        except ProviderAccessError as error:
            return error

    @staticmethod
    def _build_statistic_result(
        player: Player,
        team_name: str,
        market: PlayerMarket,
        statistics: Sequence[VerifiedPlayerMatchStatistics],
    ) -> PlayerOpportunityResult:
        values = [getattr(statistic, market.key) for statistic in statistics]
        numeric_values = [value for value in values if value is not None]
        minutes = [statistic.minutes for statistic in statistics if statistic.minutes is not None]
        ratings = [statistic.rating for statistic in statistics if statistic.rating is not None]
        individual_matches = tuple(
            PlayerOpportunityService._serialize_verified_match(statistic)
            for statistic in statistics
        )
        if not numeric_values:
            return PlayerOpportunityResult(
                kind="player_opportunity",
                answer=(
                    f"A fonte não encontrou jogos com {market.label} "
                    f"verificáveis para {player.name}."
                ),
                player=player.name,
                team=team_name,
                market=market.label,
                status="insufficient_coverage",
                recommendation="sem dados",
                threshold=1,
                average_metric=None,
                hit_rate=None,
                appearances_considered=len(statistics),
                average_minutes=round(mean(minutes), 1) if minutes else None,
                average_rating=round(mean(ratings), 2) if ratings else None,
                next_match=None,
                appearances=(),
                individual_matches=individual_matches,
                insight="A fonte não registrou a métrica individual nas partidas retornadas.",
            )

        average = round(mean(numeric_values), 2)
        hit_rate = round(sum(value >= 1 for value in numeric_values) / len(numeric_values) * 100, 1)
        observed_seasons = sorted({statistic.season for statistic in statistics if statistic.season is not None})
        season_note = f" na temporada {observed_seasons[-1]}" if len(observed_seasons) == 1 else ""
        is_short_sample = len(numeric_values) < 3
        return PlayerOpportunityResult(
            kind="player_opportunity",
            answer=(
                f"Nos últimos {len(numeric_values)} jogos com dados individuais verificados, "
                f"{player.name} teve média de {average:.2f} {market.label} por partida{season_note}."
                f"{' A amostra é curta e serve apenas como referência.' if is_short_sample else ''}"
            ),
            player=player.name,
            team=team_name,
            market=market.label,
            status="ready",
            recommendation="amostra curta" if is_short_sample else "dados verificados",
            threshold=1,
            average_metric=average,
            hit_rate=hit_rate,
            appearances_considered=len(statistics),
            average_minutes=round(mean(minutes), 1) if minutes else None,
            average_rating=round(mean(ratings), 2) if ratings else None,
            next_match=None,
            appearances=(),
            individual_matches=individual_matches,
            insight=(
                f"A média considera somente os {len(numeric_values)} jogos em que a fonte registrou "
                f"{market.label} de forma individual."
                f"{' São menos de três jogos, então não é uma base para recomendação.' if is_short_sample else ''}"
            ),
        )

    @staticmethod
    def _market_for_question(question: str) -> PlayerMarket:
        normalized = normalize_text(question)
        if "no alvo" in normalized or "no gol" in normalized or "ao gol" in normalized:
            return _MARKETS[0]
        if "falta" in normalized:
            return _MARKETS[1]
        if "cartao" in normalized:
            return _MARKETS[2]
        return _MARKETS[3]

    @staticmethod
    def _threshold_for_question(question: str) -> int:
        match = re.search(
            r"(?:mais de|acima de|over)\s*(\d+(?:[\.,]\d+)?)",
            normalize_text(question),
        )
        if match is None:
            return 1
        return max(1, floor(float(match.group(1).replace(",", "."))) + 1)

    @staticmethod
    def _evaluate_verified(
        market: PlayerMarket,
        threshold: int,
        statistics: Sequence[VerifiedPlayerMatchStatistics],
        average_minutes: float | None,
    ) -> tuple[str, float, float, str, str] | None:
        values = [
            (statistic, getattr(statistic, market.key))
            for statistic in statistics
            if getattr(statistic, market.key) is not None
        ]
        if len(values) < 3:
            return None
        numeric_values = [value for _, value in values if value is not None]
        average_metric = round(mean(numeric_values), 2)
        hit_rate = round(sum(value >= threshold for value in numeric_values) / len(numeric_values) * 100, 1)
        if hit_rate >= 70 and (average_minutes is None or average_minutes >= 55):
            recommendation = "favorável"
        elif hit_rate >= 40:
            recommendation = "neutro"
        else:
            recommendation = "evitar"
        answer = (
            f"Perfil {recommendation} para {market.singular_label} {threshold}+ no histórico recente: "
            f"média de {average_metric:.2f} e ocorrência em {hit_rate:.1f}% de {len(numeric_values)} jogos com dado individual."
        )
        insight = (
            f"A leitura compara somente a linha de {threshold}+ {market.label} com partidas em que a métrica foi registrada. "
            "Ela não considera odds, escalação confirmada nem garante resultado; revise o contexto do jogo antes de decidir."
        )
        return recommendation, average_metric, hit_rate, answer, insight

    @staticmethod
    def _narrate(
        player: Player,
        team: Team,
        appearances: Sequence[PlayerAppearance],
        played: Sequence[PlayerAppearance],
        average_minutes: float | None,
        average_rating: float | None,
        next_match: dict[str, object] | None,
        market: PlayerMarket,
        status: str,
    ) -> tuple[str, str]:
        next_match_text = ""
        if next_match:
            next_match_text = (
                f" O próximo jogo listado é {next_match['home_team']} x "
                f"{next_match['away_team']} em {next_match['date']}."
            )
        if not played:
            return (
                f"Ainda não há base de minutos recente para avaliar {player.name} em {market.label}."
                f"{next_match_text}",
                "Sem minutos confirmados, o ScoreFlash não transforma a presença no elenco em recomendação.",
            )
        details = f"{len(played)} participações com minutos em {len(appearances)} registros recentes"
        if average_minutes is not None:
            details += f", com {average_minutes:.1f} minutos de média"
        if average_rating is not None:
            details += f" e rating médio {average_rating:.2f}"
        if status == "needs_provider_key":
            reason = (
                "A integração de métricas individuais está pronta, mas ainda falta a chave local da API-Football. "
                "Por isso o ScoreFlash não recomenda a prop com base apenas em minutos e rating."
            )
        elif status == "provider_unavailable":
            reason = (
                "A fonte de métricas individuais não respondeu nesta tentativa. "
                "O ScoreFlash não converte minutos e rating em uma recomendação de prop."
            )
        else:
            reason = (
                f"A fonte não trouxe ao menos três jogos com {market.label} individuais verificáveis. "
                "O ScoreFlash prefere não recomendar uma prop com amostra fraca."
            )
        return (f"{player.name} tem {details} pelo {team.name}.{next_match_text}", reason)

    @staticmethod
    def _serialize_appearance(appearance: PlayerAppearance) -> dict[str, object]:
        return {
            "id": appearance.event_id,
            "date": appearance.kickoff.astimezone(UTC).date().isoformat(),
            "home_team": appearance.home_team,
            "away_team": appearance.away_team,
            "competition": appearance.competition,
            "minutes": appearance.minutes,
            "rating": appearance.rating,
        }

    @staticmethod
    def _serialize_verified_match(statistic: VerifiedPlayerMatchStatistics) -> dict[str, object]:
        return {
            "id": str(statistic.fixture_id),
            "date": statistic.date.astimezone(UTC).date().isoformat(),
            "home_team": statistic.home_team,
            "away_team": statistic.away_team,
            "competition": statistic.competition,
            "minutes": statistic.minutes,
            "rating": statistic.rating,
            "shots_total": statistic.shots_total,
            "shots_on_target": statistic.shots_on_target,
            "fouls_committed": statistic.fouls_committed,
            "fouls_drawn": statistic.fouls_drawn,
            "yellow_cards": statistic.yellow_cards,
            "red_cards": statistic.red_cards,
        }
