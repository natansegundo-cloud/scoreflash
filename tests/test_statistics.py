from datetime import UTC, datetime
import unittest

from scoreflash.errors import InsufficientDataError
from scoreflash.models import Match, StatisticQuery, Team, Venue
from scoreflash.services.narration import narrate_average
from scoreflash.services.insights import build_team_insight, confidence_for_sample
from scoreflash.services.statistics import calculate_average


class StatisticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.flamengo = Team("demo", "fla", "Flamengo")
        self.opponent = Team("demo", "opp", "Adversário")
        self.matches = tuple(
            Match(
                external_id=f"match-{index}",
                kickoff=datetime(2026, 9, 10 - index, tzinfo=UTC),
                home_team=self.flamengo,
                away_team=self.opponent,
                finished=True,
                statistics={"total_de_finalizacoes": (shots, 9.0)},
            )
            for index, shots in enumerate((18, 14, 16, 17, 15), start=1)
        )

    def test_calculates_average_for_last_home_matches(self) -> None:
        query = StatisticQuery(self.flamengo, "finalizações", games=5, venue=Venue.HOME)

        result = calculate_average(query, self.matches)

        self.assertEqual(result.average, 16.0)
        self.assertEqual(len(result.matches_used), 5)
        self.assertEqual(
            narrate_average(result),
            "Nos últimos 5 jogos em casa, Flamengo teve média de 16 finalizações por partida.",
        )

    def test_rejects_incomplete_sample(self) -> None:
        query = StatisticQuery(self.flamengo, "escanteios", games=5, venue=Venue.HOME)

        with self.assertRaises(InsufficientDataError):
            calculate_average(query, self.matches)

    def test_uses_the_available_sample_when_one_match_has_no_statistic(self) -> None:
        matches = self.matches[:-1]
        query = StatisticQuery(self.flamengo, "finalizações", games=5, venue=Venue.HOME)

        result = calculate_average(query, matches)

        self.assertEqual(len(result.matches_used), 4)
        self.assertEqual(result.average, 16.25)
        self.assertIn("4 jogos disponíveis", narrate_average(result))

    def test_filters_the_requested_competition(self) -> None:
        league_match = Match(
            external_id="league-match",
            kickoff=datetime(2026, 9, 10, tzinfo=UTC),
            home_team=self.flamengo,
            away_team=self.opponent,
            finished=True,
            statistics={"total_de_finalizacoes": (12.0, 8.0)},
            competition_name="Inglaterra: Premier League",
        )
        cup_match = Match(
            external_id="cup-match",
            kickoff=datetime(2026, 9, 9, tzinfo=UTC),
            home_team=self.flamengo,
            away_team=self.opponent,
            finished=True,
            statistics={"total_de_finalizacoes": (20.0, 8.0)},
            competition_name="Inglaterra: FA Cup",
        )

        result = calculate_average(
            StatisticQuery(
                self.flamengo,
                "finalizações",
                games=5,
                venue=Venue.HOME,
                competition_name="Premier League",
            ),
            (league_match, cup_match),
        )

        self.assertEqual(result.average, 12.0)
        self.assertEqual([match.external_id for match in result.matches_used], ["league-match"])

    def test_recognizes_user_friendly_metric_alias(self) -> None:
        query = StatisticQuery(self.flamengo, "chutes", games=5, venue=Venue.HOME)

        result = calculate_average(query, self.matches)

        self.assertEqual(result.average, 16.0)

    def test_builds_human_insight_from_the_observed_sample(self) -> None:
        result = calculate_average(
            StatisticQuery(self.flamengo, "finalizações", games=5, venue=Venue.HOME),
            self.matches,
        )

        insight = build_team_insight(result)

        self.assertIn("5 jogos", insight)
        self.assertIn("Confiança média", insight)
        self.assertEqual(confidence_for_sample(8), "alta")
