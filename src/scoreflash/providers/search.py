"""Descoberta de equipes pelo serviço público usado pela busca do FlashScore."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..errors import ProviderAccessError

SearchTransport = Callable[[str, Mapping[str, str], float], str]


@dataclass(frozen=True, slots=True)
class SearchTeam:
    external_id: str
    name: str
    slug: str
    country: str | None
    country_id: int | None


@dataclass(frozen=True, slots=True)
class SearchPlayer:
    external_id: str
    name: str
    slug: str
    position: str | None
    country: str | None
    team_external_id: str | None
    team_name: str | None


def _default_transport(url: str, headers: Mapping[str, str], timeout: float) -> str:
    request = Request(url, headers=dict(headers))
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL constante.
            return response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as error:
        raise ProviderAccessError("Não foi possível pesquisar equipes agora.") from error


class FlashscoreSearchClient:
    """Cliente pequeno para a busca pública de participantes de futebol."""

    BASE_URL = "https://s.livesport.services/api/v2/search/"
    PROJECT_ID = 401
    PROJECT_TYPE_ID = 1
    LANGUAGE_ID = 31
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        *,
        timeout_seconds: float = 12.0,
        transport: SearchTransport = _default_transport,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def search_teams(self, query: str, *, limit: int = 10) -> tuple[SearchTeam, ...]:
        records = self._search(query, type_ids="2")
        teams: list[SearchTeam] = []
        for record in records:
            if record.get("type", {}).get("id") != 2 or record.get("sport", {}).get("id") != 1:
                continue
            external_id = record.get("id")
            name = record.get("name")
            slug = record.get("url")
            if not all(isinstance(value, str) for value in (external_id, name, slug)):
                continue
            if not re.fullmatch(r"[A-Za-z0-9]+", external_id) or not re.fullmatch(r"[a-z0-9-]+", slug):
                continue
            country_record = record.get("defaultCountry")
            country = country_record.get("name") if isinstance(country_record, dict) else None
            country_id = country_record.get("id") if isinstance(country_record, dict) else None
            teams.append(
                SearchTeam(
                    external_id=external_id,
                    name=name,
                    slug=slug,
                    country=country if isinstance(country, str) else None,
                    country_id=country_id if isinstance(country_id, int) else None,
                )
            )
            if len(teams) == limit:
                break
        return tuple(teams)

    def search_players(self, query: str, *, limit: int = 10) -> tuple[SearchPlayer, ...]:
        """Pesquisa atletas de futebol e retorna o vínculo exibido pela fonte.

        Os tipos 3 e 4 cobrem resultados de jogador independentes e jogadores
        apresentados dentro de uma equipe. O segundo é o formato hoje usado
        para atletas como Léo Ortiz.
        """
        records = self._search(query, type_ids="3,4")
        players: list[SearchPlayer] = []
        for record in records:
            type_id = record.get("type", {}).get("id")
            if type_id not in {3, 4} or record.get("sport", {}).get("id") != 1:
                continue
            external_id = record.get("id")
            name = record.get("name")
            slug = record.get("url")
            if not all(isinstance(value, str) for value in (external_id, name, slug)):
                continue
            if not re.fullmatch(r"[A-Za-z0-9]+", external_id) or not re.fullmatch(r"[a-z0-9-]+", slug):
                continue
            participant_types = record.get("participantTypes")
            if isinstance(participant_types, dict):
                position = participant_types.get("name")
            elif (
                isinstance(participant_types, list)
                and participant_types
                and isinstance(participant_types[0], dict)
            ):
                position = participant_types[0].get("name")
            else:
                position = None
            country_record = record.get("defaultCountry")
            country = country_record.get("name") if isinstance(country_record, dict) else None
            teams = record.get("teams")
            team = teams[0] if isinstance(teams, list) and teams and isinstance(teams[0], dict) else {}
            team_external_id = team.get("id")
            team_name = team.get("name")
            players.append(
                SearchPlayer(
                    external_id=external_id,
                    name=name,
                    slug=slug,
                    position=position if isinstance(position, str) else None,
                    country=country if isinstance(country, str) else None,
                    team_external_id=team_external_id if isinstance(team_external_id, str) else None,
                    team_name=team_name if isinstance(team_name, str) else None,
                )
            )
            if len(players) == limit:
                break
        return tuple(players)

    def _search(self, query: str, *, type_ids: str) -> list[dict[str, object]]:
        clean_query = " ".join(query.split())
        if not 2 <= len(clean_query) <= 80:
            return []

        parameters = urlencode(
            {
                "q": clean_query,
                "lang-id": self.LANGUAGE_ID,
                "type-ids": type_ids,
                "project-id": self.PROJECT_ID,
                "project-type-id": self.PROJECT_TYPE_ID,
                "sport-ids": "1",
            }
        )
        payload = self._transport(
            f"{self.BASE_URL}?{parameters}",
            {"User-Agent": self.USER_AGENT, "Referer": "https://www.flashscore.com.br/"},
            self._timeout_seconds,
        )
        try:
            records = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ProviderAccessError("A busca de equipes devolveu um formato inválido.") from error
        if not isinstance(records, list):
            raise ProviderAccessError("A busca de equipes devolveu um formato inesperado.")
        return [record for record in records if isinstance(record, dict)]
