import json
import unittest
from urllib.parse import parse_qs, urlparse

from scoreflash.providers.api_football import (
    ApiFootballHeadToHeadClient,
    ApiFootballPlayerStatisticsClient,
)


class ApiFootballClientTests(unittest.TestCase):
    def test_resolves_teams_and_returns_brasileirao_head_to_head_matches(self) -> None:
        calls: list[str] = []

        def transport(url: str, headers: dict[str, str], timeout: float) -> str:
            calls.append(url)
            endpoint = urlparse(url).path.lstrip("/")
            query = parse_qs(urlparse(url).query)
            if endpoint == "teams":
                name = query["search"][0]
                response = (
                    {"response": [{"team": {"id": 1, "name": "Gremio", "country": "Brazil"}}]}
                    if name == "gremio"
                    else {"response": [{"team": {"id": 2, "name": "Vasco DA Gama", "country": "Brazil"}}]}
                )
                return json.dumps(response)
            self.assertEqual(endpoint, "fixtures/headtohead")
            return json.dumps(
                {
                    "response": [
                        {
                            "fixture": {"id": 701, "date": "2026-09-10T19:00:00+00:00", "status": {"short": "FT"}},
                            "teams": {
                                "home": {"id": 1, "name": "Gremio"},
                                "away": {"id": 2, "name": "Vasco DA Gama"},
                            },
                            "goals": {"home": 2, "away": 1},
                            "league": {"id": 71, "country": "Brazil", "name": "Serie A"},
                        }
                    ]
                }
            )

        history = ApiFootballHeadToHeadClient("test-key", transport=transport).recent_matches(
            "gremio",
            "vasco",
            games=5,
            competition_name="campeonato brasileiro",
        )

        self.assertEqual(history.team.name, "Gremio")
        self.assertEqual(history.opponent.name, "Vasco DA Gama")
        self.assertEqual(history.matches[0].statistics["goals"], (2.0, 1.0))
        parameters = parse_qs(urlparse(calls[-1]).query)
        self.assertEqual(parameters["h2h"], ["1-2"])
        self.assertNotIn("last", parameters)
        self.assertNotIn("league", parameters)

    def test_resolves_player_and_parses_verified_fixture_statistics(self) -> None:
        calls: list[tuple[str, dict[str, str]]] = []
        responses = {
            "teams": {
                "response": [{"team": {"id": 127, "name": "Flamengo"}}]
            },
            "players": {
                "response": [
                    {
                        "player": {"id": 88, "name": "Léo Ortiz"},
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
        player_call = next(url for url, _ in calls if urlparse(url).path.endswith("/players"))
        self.assertEqual(parse_qs(urlparse(player_call).query)["team"], ["127"])
        fixture_call = next(url for url, _ in calls if urlparse(url).path.endswith("/fixtures"))
        self.assertNotIn("last", parse_qs(urlparse(fixture_call).query))

    def test_resolves_player_statistics_with_the_resolved_current_team(self) -> None:
        responses = {
            "teams": {
                "response": [{"team": {"id": 541, "name": "Real Madrid"}}]
            },
            "players": {
                "response": [
                    {
                        "player": {"id": 88, "name": "J. Bellingham"},
                    }
                ]
            },
            "fixtures": {
                "response": [
                    {
                        "fixture": {"id": 701, "date": "2026-09-10T19:00:00+00:00", "status": {"short": "FT"}},
                        "teams": {"home": {"name": "Real Madrid"}, "away": {"name": "Barcelona"}},
                        "league": {"name": "La Liga"},
                    }
                ]
            },
            "fixtures/players": {
                "response": [
                    {
                        "players": [
                            {
                                "player": {"id": 88, "name": "Jude Bellingham"},
                                "statistics": [
                                    {
                                        "games": {"minutes": 85, "rating": "7.4"},
                                        "shots": {"total": 3, "on": 2},
                                        "fouls": {"committed": 0, "drawn": 1},
                                        "cards": {"yellow": 0, "red": 0},
                                    }
                                ],
                            }
                        ]
                    }
                ]
            },
        }

        def transport(url: str, headers: dict[str, str], timeout: float) -> str:
            return json.dumps(responses[urlparse(url).path.lstrip("/")])

        statistics = ApiFootballPlayerStatisticsClient(
            "test-key", transport=transport
        ).recent_statistics("Bellingham Jude", "Real Madrid", games=3)

        self.assertEqual(statistics[0].shots_on_target, 2)
