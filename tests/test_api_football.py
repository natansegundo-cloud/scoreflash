import json
import unittest
from urllib.parse import parse_qs, urlparse

from scoreflash.providers.api_football import ApiFootballPlayerStatisticsClient


class ApiFootballClientTests(unittest.TestCase):
    def test_resolves_player_and_parses_verified_fixture_statistics(self) -> None:
        calls: list[tuple[str, dict[str, str]]] = []
        responses = {
            "players": {
                "response": [
                    {
                        "player": {"id": 88, "name": "Léo Ortiz"},
                        "statistics": [{"team": {"id": 127, "name": "Flamengo"}}],
                    }
                ]
            },
            "fixtures": {
                "response": [
                    {
                        "fixture": {"id": 701, "date": "2026-09-10T19:00:00+00:00", "status": {"short": "FT"}},
                        "teams": {"home": {"name": "Flamengo"}, "away": {"name": "Palmeiras"}},
                        "league": {"name": "Brasileirão"},
                    }
                ]
            },
            "fixtures/players": {
                "response": [
                    {
                        "players": [
                            {
                                "player": {"id": 88, "name": "Léo Ortiz"},
                                "statistics": [
                                    {
                                        "games": {"minutes": 90, "rating": "7.3"},
                                        "shots": {"total": 2, "on": 1},
                                        "fouls": {"committed": 1, "drawn": 0},
                                        "cards": {"yellow": 1, "red": 0},
                                    }
                                ],
                            }
                        ]
                    }
                ]
            },
        }

        def transport(url: str, headers: dict[str, str], timeout: float) -> str:
            calls.append((url, headers))
            endpoint = urlparse(url).path.lstrip("/")
            return json.dumps(responses[endpoint])

        client = ApiFootballPlayerStatisticsClient("test-key", transport=transport)
        statistics = client.recent_statistics("Léo Ortiz", "Flamengo", games=3)

        self.assertEqual(statistics[0].shots_total, 2)
        self.assertEqual(statistics[0].shots_on_target, 1)
        self.assertEqual(statistics[0].fouls_committed, 1)
        self.assertEqual(statistics[0].yellow_cards, 1)
        self.assertEqual(calls[0][1]["x-apisports-key"], "test-key")
        self.assertEqual(parse_qs(urlparse(calls[1][0]).query)["team"], ["127"])
