import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, urlparse

from scoreflash.providers.search import FlashscoreSearchClient, SearchTeam
from scoreflash.services.discovery import TeamDiscoveryService
from scoreflash.storage.sqlite import TeamIndex


class FakeTeamSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search_teams(self, query: str, *, limit: int = 10) -> tuple[SearchTeam, ...]:
        self.queries.append(query)
        if query != "flamengo":
            return ()
        return (
            SearchTeam(
                external_id="WjxY29qB",
                name="Flamengo",
                slug="flamengo",
                country="Brasil",
                country_id=39,
            ),
        )


class SearchTests(unittest.TestCase):
    def test_parses_public_team_search_response(self) -> None:
        captured: dict[str, object] = {}
        payload = json.dumps(
            [
                {
                    "id": "WjxY29qB",
                    "url": "flamengo",
                    "name": "Flamengo",
                    "type": {"id": 2, "name": "Team"},
                    "sport": {"id": 1, "name": "Football"},
                    "defaultCountry": {"id": 39, "name": "Brasil"},
                }
            ]
        )

        def transport(url: str, headers: dict[str, str], timeout: float) -> str:
            captured["url"] = url
            captured["headers"] = headers
            return payload

        teams = FlashscoreSearchClient(transport=transport).search_teams("Flamengo")

        params = parse_qs(urlparse(str(captured["url"])).query)
        self.assertEqual(params["q"], ["Flamengo"])
        self.assertEqual(params["type-ids"], ["2"])
        self.assertEqual(teams[0].external_id, "WjxY29qB")
        self.assertEqual(teams[0].country_id, 39)

    def test_discovers_and_remembers_team_mentioned_in_question(self) -> None:
        with TemporaryDirectory() as directory:
            index = TeamIndex(Path(directory) / "scoreflash.sqlite3")
            try:
                search = FakeTeamSearch()
                service = TeamDiscoveryService(index, search)
                team = service.resolve(
                    "Qual a média de finalizações do Flamengo nos últimos 5 jogos?"
                )

                self.assertEqual(team.name, "Flamengo")
                self.assertIn("flamengo", search.queries)
                self.assertEqual(index.resolve("flashscore", "flamengo").external_id, "WjxY29qB")
            finally:
                index.close()

    def test_parses_public_player_search_response(self) -> None:
        payload = json.dumps(
            [
                {
                    "id": "Sx6m4B4C",
                    "url": "leo-ortiz",
                    "name": "Léo Ortiz",
                    "type": {"id": 4, "name": "PlayerInTeam"},
                    "sport": {"id": 1, "name": "Football"},
                    "participantTypes": [{"name": "Defensor"}],
                    "defaultCountry": {"id": 39, "name": "Brasil"},
                    "teams": [{"id": "WjxY29qB", "name": "Flamengo"}],
                }
            ]
        )

        players = FlashscoreSearchClient(transport=lambda *_: payload).search_players("leo ortiz")

        self.assertEqual(players[0].name, "Léo Ortiz")
        self.assertEqual(players[0].team_name, "Flamengo")
        self.assertEqual(players[0].position, "Defensor")
