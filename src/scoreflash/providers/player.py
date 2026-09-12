"""Perfil público de jogador e presenças recentes no FlashScore."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from ..errors import ProviderAccessError
from ..models import Player
from .flashscore import FlashscoreClient, Transport

_MINUTES_RE = re.compile(r"\d+")


@dataclass(frozen=True, slots=True)
class PlayerAppearance:
    event_id: str
    kickoff: datetime
    home_team: str
    away_team: str
    competition: str | None
    minutes: int | None
    rating: float | None


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    player: Player
    appearances: tuple[PlayerAppearance, ...]


def extract_json_assignment(html: str, assignment: str) -> dict[str, object]:
    """Lê um objeto JSON de uma atribuição JavaScript sem executar a página."""
    marker = f"{assignment} = "
    start = html.find(marker)
    if start < 0:
        raise ProviderAccessError("A página pública do jogador mudou de formato.")
    try:
        decoded, _ = json.JSONDecoder().raw_decode(html[start + len(marker) :])
    except json.JSONDecodeError as error:
        raise ProviderAccessError("Os dados públicos do jogador vieram em formato inválido.") from error
    if not isinstance(decoded, dict):
        raise ProviderAccessError("A página pública do jogador não trouxe um perfil válido.")
    return decoded


def _parse_minutes(stats: object) -> int | None:
    if not isinstance(stats, dict):
        return None
    for stat in stats.values():
        if not isinstance(stat, dict) or stat.get("type") != "minutes-played":
            continue
        value = stat.get("value")
        if not isinstance(value, str):
            continue
        match = _MINUTES_RE.search(value)
        return int(match.group(0)) if match else None
    return None


def _parse_rating(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def _parse_kickoff(value: object) -> datetime | None:
    if isinstance(value, int):
        try:
            return datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        if value.isdigit():
            return _parse_kickoff(int(value))
        # A página de perfil localiza a data como ``11.09.26`` em vez de Unix.
        try:
            return datetime.strptime(value, "%d.%m.%y").replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def parse_player_appearances(payload: Mapping[str, object]) -> tuple[PlayerAppearance, ...]:
    last_matches_data = payload.get("lastMatchesData")
    if not isinstance(last_matches_data, dict):
        return ()
    records = last_matches_data.get("lastMatches")
    if not isinstance(records, list):
        return ()

    appearances: list[PlayerAppearance] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        event_id = record.get("eventEncodedId")
        timestamp = record.get("eventStartTime")
        home_team = record.get("homeParticipantName")
        away_team = record.get("awayParticipantName")
        if not all(isinstance(value, str) for value in (event_id, home_team, away_team)):
            continue
        if not re.fullmatch(r"[A-Za-z0-9]+", event_id):
            continue
        kickoff = _parse_kickoff(timestamp)
        if kickoff is None:
            continue
        competition = record.get("tournamentTitle")
        appearances.append(
            PlayerAppearance(
                event_id=event_id,
                kickoff=kickoff,
                home_team=home_team,
                away_team=away_team,
                competition=competition if isinstance(competition, str) else None,
                minutes=_parse_minutes(record.get("stats")),
                rating=_parse_rating(record.get("rating")),
            )
        )
    return tuple(appearances)


class FlashscorePlayerClient:
    """Consulta o perfil público, sem navegador controlado ou cookies."""

    PAGE_URL = "https://www.flashscore.com.br/jogador/{slug}/{player_id}/"

    def __init__(
        self,
        *,
        timeout_seconds: float = 12.0,
        transport: Transport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._transport = transport or FlashscoreClient()._transport

    def fetch_profile(self, player: Player) -> PlayerProfile:
        if not re.fullmatch(r"[A-Za-z0-9]+", player.external_id):
            raise ValueError("external_id do jogador contém caracteres inválidos.")
        if not re.fullmatch(r"[a-z0-9-]+", player.participant_slug):
            raise ValueError("participant_slug do jogador contém caracteres inválidos.")
        url = self.PAGE_URL.format(slug=player.participant_slug, player_id=player.external_id)
        html = self._transport(
            url,
            {"User-Agent": FlashscoreClient.DEFAULT_USER_AGENT, **FlashscoreClient.PAGE_HEADERS},
            self._timeout_seconds,
        )
        payload = extract_json_assignment(html, "window.playerProfilePageEnvironment")
        return PlayerProfile(player=player, appearances=parse_player_appearances(payload))
