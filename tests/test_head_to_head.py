from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scoreflash.config import Settings
from scoreflash.models import Match, Team
from scoreflash.providers.api_football import ApiFootballHeadToHeadHistory
from scoreflash.services.questions import HeadToHeadResult, QueryService
from scoreflash.storage.sqlite import QueryCache, TeamIndex


class FakeHeadToHeadProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, str]] = []
        self.gremio = Team("api-football", "1", "Gremio")
        self.vasco = Team("api-football", "2", "Vasco DA Gama")

    def recent_matches(
        self,
        team_name: str,
        opponent_name: str,
        *,
        games: int,
        competition_name: str = "",
    ) -> ApiFootballHeadToHeadHistory:
        self.calls.append((team_name, opponent_name, games, competition_name))
        matches = (
            Match(
                external_id="h2h-1",
                kickoff=datetime(2026, 9, 10, tzinfo=UTC),
                home_team=self.gremio,
                away_team=self.vasco,
                finished=True,
                statistics={"goals": (2.0, 1.0)},
                competition_name="Brazil: Serie A",
            ),
            Match(
                external_id="h2h-2",
                kickoff=datetime(2026, 9, 2, tzinfo=UTC),
                home_team=self.gremio,
                away_team=self.vasco,
                finished=True,
                statistics={"goals": (1.0, 1.0)},
                competition_name="Brazil: Serie A",
            ),
            Match(
                external_id="h2h-3",
                kickoff=datetime(2026, 8, 24, tzinfo=UTC),
                home_team=self.vasco,
                away_team=self.gremio,
                finished=True,
                statistics={"goals": (3.0, 0.0)},
                competition_name="Brazil: Serie A",
            ),
        )
        return ApiFootballHeadToHeadHistory(self.gremio, self.vasco, matches)


class HeadToHeadQueryTests(unittest.TestCase):
    def test_calculates_goals_with_primary_team_as_home_side_and_caches_result(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "scoreflash.sqlite3"
            teams = TeamIndex(database)
            cache = QueryCache(database)
            provider = FakeHeadToHeadProvider()
            service = QueryService(
                Settings(flashscore_signature="", data_dir=Path(directory)),
                teams,
                cache,
                head_to_head=provider,
            )
            question = (
                "qual a media de gols no confronto gremio e vasco sendo gremio "
                "o mandante pelo campeonato brasileiro"
            )
            try:
                result = service.execute(question)
                cached_result = service.execute(question)
            finally:
                service.close()

        self.assertIsInstance(result, HeadToHeadResult)
        self.assertEqual(result.kind, "head_to_head")
        self.assertEqual(result.team, "Gremio")
        self.assertEqual(result.opponent, "Vasco DA Gama")
        self.assertEqual(result.games, 2)
        self.assertEqual(result.team_average, 1.5)
        self.assertEqual(result.opponent_average, 1.0)
        self.assertEqual(result.average, 2.5)
        self.assertIn("mandante", result.answer)
        self.assertEqual(provider.calls, [("gremio", "vasco", 5, "brasileirao")])
        self.assertIsInstance(cached_result, HeadToHeadResult)
        self.assertTrue(cached_result.cached)
