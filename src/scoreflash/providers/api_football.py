"""Estatísticas individuais verificadas via API-Football.

Este adaptador só é ativado quando existe uma chave local. Ele não compartilha
a chave com o navegador e consulta poucos jogos sob demanda.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..errors import ProviderAccessError
from ..normalization import normalize_text

Transport = Callable[[str, Mapping[str, str], float], str]


@dataclass(frozen=True, slots=True)
class VerifiedPlayerMatchStatistics:
    fixture_id: int
    date: datetime
    home_team: str
    away_team: str
    competition: str | None
    minutes: int | None
    rating: float | None
    shots_total: int | None
    shots_on_target: int | None
    fouls_committed: int | None
    fouls_drawn: int | None
    yellow_cards: int | None
    red_cards: int | None


@dataclass(frozen=True, slots=True)
class _ApiFootballPlayer:
    player_id: int
    name: str
    team_id: int
    team_name: str


def _default_transport(url: str, headers: Mapping[str, str], timeout: float) -> str:
    request = Request(url, headers=dict(headers))
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL constante.
            return response.read().decode("utf-8")
    except HTTPError as error:
        if error.code in {401, 403}:
            raise ProviderAccessError(
                "A chave de estatísticas individuais não foi aceita. Confira API_FOOTBALL_API_KEY."
            ) from error
        if error.code == 429:
            raise ProviderAccessError(
                "O limite diário de estatísticas individuais foi atingido. Tente novamente mais tarde."
            ) from error
        raise ProviderAccessError(f"A fonte de estatísticas individuais respondeu HTTP {error.code}.") from error
    except (URLError, TimeoutError) as error:
        raise ProviderAccessError("Não foi possível consultar as estatísticas individuais agora.") from error


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


class ApiFootballPlayerStatisticsClient:
    """Cliente de baixa escala para rendimento individual por partida."""

    BASE_URL = "https://v3.football.api-sports.io"
    FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 15.0,
        transport: Transport = _default_transport,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key da API-Football não pode estar vazia.")
        self._api_key = api_key.strip()
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def recent_statistics(
        self,
        player_name: str,
        team_name: str,
        *,
        games: int = 5,
    ) -> tuple[VerifiedPlayerMatchStatistics, ...]:
        if not 3 <= games <= 10:
            raise ValueError("games deve estar entre 3 e 10.")
        player = self._resolve_player(player_name, team_name)
        fixtures = self._request("fixtures", {"team": player.team_id, "last": games})
        statistics: list[VerifiedPlayerMatchStatistics] = []
        for fixture in self._finished_fixtures(fixtures):
            statistic = self._player_statistic_for_fixture(fixture, player)
            if statistic is not None:
                statistics.append(statistic)
        return tuple(sorted(statistics, key=lambda item: item.date, reverse=True))

    def _resolve_player(self, player_name: str, team_name: str) -> _ApiFootballPlayer:
        response = self._request("players", {"search": player_name})
        target_player = normalize_text(player_name)
        target_team = normalize_text(team_name)
        candidates: list[_ApiFootballPlayer] = []
        for item in response:
            if not isinstance(item, dict):
                continue
            player = item.get("player")
            if not isinstance(player, dict) or normalize_text(str(player.get("name", ""))) != target_player:
                continue
            entries = item.get("statistics")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                team = entry.get("team")
                if not isinstance(team, dict) or normalize_text(str(team.get("name", ""))) != target_team:
                    continue
                player_id = _as_int(player.get("id"))
                team_id = _as_int(team.get("id"))
                name = player.get("name")
                resolved_team_name = team.get("name")
                if player_id is None or team_id is None or not isinstance(name, str) or not isinstance(resolved_team_name, str):
                    continue
                candidates.append(_ApiFootballPlayer(player_id, name, team_id, resolved_team_name))
        if not candidates:
            raise ProviderAccessError(
                f"A fonte de estatísticas individuais não encontrou {player_name} no {team_name}."
            )
        return candidates[0]

    def _finished_fixtures(self, response: list[object]) -> tuple[dict[str, object], ...]:
        fixtures: list[dict[str, object]] = []
        for item in response:
            if not isinstance(item, dict):
                continue
            fixture = item.get("fixture")
            status = fixture.get("status") if isinstance(fixture, dict) else None
            if not isinstance(status, dict) or status.get("short") not in self.FINISHED_STATUSES:
                continue
            fixtures.append(item)
        return tuple(fixtures)

    def _player_statistic_for_fixture(
        self,
        fixture: Mapping[str, object],
        player: _ApiFootballPlayer,
    ) -> VerifiedPlayerMatchStatistics | None:
        fixture_data = fixture.get("fixture")
        teams = fixture.get("teams")
        league = fixture.get("league")
        if not isinstance(fixture_data, dict) or not isinstance(teams, dict):
            return None
        fixture_id = _as_int(fixture_data.get("id"))
        date_raw = fixture_data.get("date")
        home = teams.get("home")
        away = teams.get("away")
        if (
            fixture_id is None
            or not isinstance(date_raw, str)
            or not isinstance(home, dict)
            or not isinstance(away, dict)
            or not isinstance(home.get("name"), str)
            or not isinstance(away.get("name"), str)
        ):
            return None
        try:
            date = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        response = self._request("fixtures/players", {"fixture": fixture_id})
        for team_data in response:
            if not isinstance(team_data, dict):
                continue
            players = team_data.get("players")
            if not isinstance(players, list):
                continue
            for player_data in players:
                if not isinstance(player_data, dict):
                    continue
                identity = player_data.get("player")
                if not isinstance(identity, dict) or _as_int(identity.get("id")) != player.player_id:
                    continue
                entries = player_data.get("statistics")
                if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
                    continue
                stat = entries[0]
                games = stat.get("games") if isinstance(stat.get("games"), dict) else {}
                shots = stat.get("shots") if isinstance(stat.get("shots"), dict) else {}
                fouls = stat.get("fouls") if isinstance(stat.get("fouls"), dict) else {}
                cards = stat.get("cards") if isinstance(stat.get("cards"), dict) else {}
                competition = league.get("name") if isinstance(league, dict) else None
                return VerifiedPlayerMatchStatistics(
                    fixture_id=fixture_id,
                    date=date,
                    home_team=home["name"],
                    away_team=away["name"],
                    competition=competition if isinstance(competition, str) else None,
                    minutes=_as_int(games.get("minutes")),
                    rating=_as_float(games.get("rating")),
                    shots_total=_as_int(shots.get("total")),
                    shots_on_target=_as_int(shots.get("on")),
                    fouls_committed=_as_int(fouls.get("committed")),
                    fouls_drawn=_as_int(fouls.get("drawn")),
                    yellow_cards=_as_int(cards.get("yellow")),
                    red_cards=_as_int(cards.get("red")),
                )
        return None

    def _request(self, endpoint: str, parameters: Mapping[str, object]) -> list[object]:
        payload = self._transport(
            f"{self.BASE_URL}/{endpoint}?{urlencode(parameters)}",
            {
                "Accept": "application/json",
                "User-Agent": "ScoreFlash/0.1 personal analytics",
                "x-apisports-key": self._api_key,
            },
            self._timeout_seconds,
        )
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ProviderAccessError("A fonte de estatísticas individuais devolveu um formato inválido.") from error
        errors = parsed.get("errors") if isinstance(parsed, dict) else None
        if errors:
            raise ProviderAccessError("A fonte de estatísticas individuais recusou a consulta.")
        response = parsed.get("response") if isinstance(parsed, dict) else None
        if not isinstance(response, list):
            raise ProviderAccessError("A fonte de estatísticas individuais devolveu uma resposta inesperada.")
        return response
