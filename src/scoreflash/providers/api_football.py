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

from ..errors import InsufficientDataError, ProviderAccessError
from ..models import Match, Team
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


@dataclass(frozen=True, slots=True)
class ApiFootballHeadToHeadHistory:
    """Dois clubes resolvidos pela API-Football e os jogos entre eles."""

    team: Team
    opponent: Team
    matches: tuple[Match, ...]


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


class ApiFootballHeadToHeadClient:
    """Consulta de confrontos diretos por placar final."""

    BASE_URL = ApiFootballPlayerStatisticsClient.BASE_URL
    FINISHED_STATUSES = ApiFootballPlayerStatisticsClient.FINISHED_STATUSES
    _BRAZILEIRAO_LEAGUE_ID = 71
    _BRAZILEIRAO_ALIASES = frozenset(
        {
            "brasileirao",
            "brasileirao serie a",
            "campeonato brasileiro",
            "campeonato brasileiro serie a",
            "serie a brasileira",
        }
    )

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

    def recent_matches(
        self,
        team_name: str,
        opponent_name: str,
        *,
        games: int,
        competition_name: str = "",
    ) -> ApiFootballHeadToHeadHistory:
        if not 1 <= games <= 10:
            raise ValueError("games deve estar entre 1 e 10.")
        team = self._resolve_team(team_name)
        opponent = self._resolve_team(opponent_name)
        if team.external_id == opponent.external_id:
            raise ProviderAccessError("Escolha dois times diferentes para comparar o confronto.")

        parameters: dict[str, object] = {
            "h2h": f"{team.external_id}-{opponent.external_id}",
            # Busca uma janela maior pois o recorte de mando é aplicado depois.
            "last": max(20, games * 4),
        }
        league_id = self._league_id_for(competition_name)
        if league_id is not None:
            parameters["league"] = league_id
        matches = tuple(
            match
            for item in self._request("fixtures/headtohead", parameters)
            if (match := self._parse_match(item)) is not None
            and team.external_id in {match.home_team.external_id, match.away_team.external_id}
            and opponent.external_id in {match.home_team.external_id, match.away_team.external_id}
        )
        if not matches:
            competition = f" pela {competition_name}" if competition_name else ""
            raise InsufficientDataError(
                f"Não encontrei confrontos encerrados entre {team.name} e {opponent.name}{competition}."
            )
        return ApiFootballHeadToHeadHistory(team=team, opponent=opponent, matches=matches)

    def _resolve_team(self, name: str) -> Team:
        target = normalize_text(name)
        candidates: list[tuple[int, int, Team]] = []
        for item in self._request("teams", {"search": name}):
            if not isinstance(item, dict):
                continue
            raw_team = item.get("team")
            raw_country = item.get("country")
            if not isinstance(raw_team, dict):
                continue
            team_id = _as_int(raw_team.get("id"))
            candidate_name = raw_team.get("name")
            if team_id is None or not isinstance(candidate_name, str):
                continue
            candidate = normalize_text(candidate_name)
            if candidate == target:
                name_rank = 0
            elif candidate.startswith(f"{target} ") or f" {target} " in f" {candidate} ":
                name_rank = 1
            else:
                continue
            country_name = raw_team.get("country")
            if not isinstance(country_name, str) and isinstance(raw_country, dict):
                country_name = raw_country.get("name")
            country = country_name if isinstance(country_name, str) else None
            country_rank = 0 if normalize_text(country or "") == "brazil" else 1
            candidates.append(
                (
                    name_rank,
                    country_rank,
                    Team(
                        provider="api-football",
                        external_id=str(team_id),
                        name=candidate_name,
                        country=country,
                    ),
                )
            )
        if not candidates:
            raise ProviderAccessError(f"A API-Football não encontrou a equipe {name!r}.")
        return min(candidates, key=lambda candidate: (candidate[0], candidate[1]))[2]

    def _league_id_for(self, competition_name: str) -> int | None:
        normalized = normalize_text(competition_name)
        if not normalized:
            return None
        if normalized in self._BRAZILEIRAO_ALIASES:
            return self._BRAZILEIRAO_LEAGUE_ID
        raise ProviderAccessError(
            "Por enquanto, o confronto direto com filtro de liga está pronto para o Brasileirão."
        )

    def _parse_match(self, item: object) -> Match | None:
        if not isinstance(item, dict):
            return None
        fixture = item.get("fixture")
        teams = item.get("teams")
        goals = item.get("goals")
        league = item.get("league")
        if not isinstance(fixture, dict) or not isinstance(teams, dict) or not isinstance(goals, dict):
            return None
        status = fixture.get("status")
        if not isinstance(status, dict) or status.get("short") not in self.FINISHED_STATUSES:
            return None
        home = teams.get("home")
        away = teams.get("away")
        fixture_id = _as_int(fixture.get("id"))
        date_raw = fixture.get("date")
        home_id = _as_int(home.get("id")) if isinstance(home, dict) else None
        away_id = _as_int(away.get("id")) if isinstance(away, dict) else None
        home_name = home.get("name") if isinstance(home, dict) else None
        away_name = away.get("name") if isinstance(away, dict) else None
        home_goals = _as_float(goals.get("home"))
        away_goals = _as_float(goals.get("away"))
        if (
            fixture_id is None
            or not isinstance(date_raw, str)
            or home_id is None
            or away_id is None
            or not isinstance(home_name, str)
            or not isinstance(away_name, str)
            or home_goals is None
            or away_goals is None
        ):
            return None
        try:
            kickoff = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        competition_name = league.get("name") if isinstance(league, dict) else None
        country = league.get("country") if isinstance(league, dict) else None
        label = (
            f"{country}: {competition_name}"
            if isinstance(country, str) and isinstance(competition_name, str)
            else competition_name if isinstance(competition_name, str) else None
        )
        return Match(
            external_id=str(fixture_id),
            kickoff=kickoff,
            home_team=Team("api-football", str(home_id), home_name),
            away_team=Team("api-football", str(away_id), away_name),
            finished=True,
            statistics={"goals": (home_goals, away_goals)},
            competition_name=label,
        )

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
            raise ProviderAccessError("A API-Football devolveu um formato inválido.") from error
        errors = parsed.get("errors") if isinstance(parsed, dict) else None
        if errors:
            raise ProviderAccessError("A API-Football recusou a consulta de confronto direto.")
        response = parsed.get("response") if isinstance(parsed, dict) else None
        if not isinstance(response, list):
            raise ProviderAccessError("A API-Football devolveu uma resposta inesperada.")
        return response
