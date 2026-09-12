from datetime import UTC, datetime
import unittest

from scoreflash.models import Match, Player, Team
from scoreflash.providers.player import PlayerAppearance, PlayerProfile
from scoreflash.providers.api_football import VerifiedPlayerMatchStatistics
from scoreflash.providers.search import SearchPlayer
from scoreflash.services.player_discovery import PlayerDiscoveryService
from scoreflash.services.player_opportunities import PlayerOpportunityService


class FakePlayerSearch:
    def search_players(self, query: str, *, limit: int = 10) -> tuple[SearchPlayer, ...]:
        if query == "jude bellingham":
            return (
                SearchPlayer(
                    external_id="JudeBellingham",
                    name="Jude Bellingham",
                    slug="jude-bellingham",
                    position="Meio-campista",
                    country="Inglaterra",
                    team_external_id="RealMadrid",
                    team_name="Real Madrid",
                ),
            )
        if query != "leo ortiz":
            return ()
        return (
            SearchPlayer(
                external_id="Sx6m4B4C",
                name="Léo Ortiz",
                slug="leo-ortiz",
                position="Defensor",
                country="Brasil",
                team_external_id="WjxY29qB",
                team_name="Flamengo",
            ),
        )


class FakeProfiles:
    def fetch_profile(self, player: Player) -> PlayerProfile:
        appearances = tuple(
            PlayerAppearance(
                event_id=f"Event{index}",
                kickoff=datetime(2026, 9, index, tzinfo=UTC),
                home_team="Flamengo",
                away_team="Palmeiras",
                competition="Brasileirão",
                minutes=90,
                rating=7.2,
            )
            for index in range(1, 4)
        )
        return PlayerProfile(player=player, appearances=appearances)


class FakeFixtures:
    class Retrieved:
        def __init__(self, match: Match) -> None:
            self.matches = (match,)

    def fetch_initial_participant_fixtures(self, *_: str) -> Retrieved:
        team = Team("flashscore", "WjxY29qB", "Flamengo", participant_slug="flamengo")
        opponent = Team("flashscore", "dGhStR5m", "Palmeiras")
        return self.Retrieved(
            Match("Next0001", datetime(2026, 9, 12, tzinfo=UTC), team, opponent, False)
        )


class FakeIndividualStatistics:
    def recent_statistics(self, *_: str, games: int = 5) -> tuple[VerifiedPlayerMatchStatistics, ...]:
        return tuple(
            VerifiedPlayerMatchStatistics(
                fixture_id=900 + index,
                date=datetime(2026, 9, index, tzinfo=UTC),
                home_team="Flamengo",
                away_team="Palmeiras",
                competition="Brasileirão",
                minutes=90,
                rating=7.0,
                shots_total=value,
                shots_on_target=1 if value else 0,
                fouls_committed=1,
                fouls_drawn=0,
                yellow_cards=0,
                red_cards=0,
            )
            for index, value in enumerate((2, 1, 0, 1, 2), start=1)
        )


class PlayerOpportunityTests(unittest.TestCase):
    def test_confirms_player_team_and_explains_missing_shot_metric(self) -> None:
        team = Team("flashscore", "WjxY29qB", "Flamengo", participant_slug="flamengo")
        service = PlayerOpportunityService(
            discovery=PlayerDiscoveryService(FakePlayerSearch()),
            profiles=FakeProfiles(),
            fixtures=FakeFixtures(),
        )

        result = service.evaluate_finalization(
            "O Léo Ortiz é uma boa ideia para finalizar no jogo de amanhã do Flamengo?",
            team,
        )

        self.assertEqual(result.player, "Léo Ortiz")
        self.assertEqual(result.status, "needs_provider_key")
        self.assertEqual(result.average_minutes, 90)
        self.assertEqual(result.next_match["away_team"], "Palmeiras")
        self.assertIn("não recomenda", result.insight)

    def test_builds_a_verified_shot_opportunity_from_individual_matches(self) -> None:
        team = Team("flashscore", "WjxY29qB", "Flamengo", participant_slug="flamengo")
        service = PlayerOpportunityService(
            discovery=PlayerDiscoveryService(FakePlayerSearch()),
            profiles=FakeProfiles(),
            fixtures=FakeFixtures(),
            individual_statistics=FakeIndividualStatistics(),
        )

        result = service.evaluate(
            "O Léo Ortiz vale mais de 0.5 finalizações amanhã pelo Flamengo?",
            team,
        )

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.recommendation, "favorável")
        self.assertEqual(result.threshold, 1)
        self.assertEqual(result.average_metric, 1.2)
        self.assertEqual(result.hit_rate, 80.0)
        self.assertEqual(len(result.individual_matches), 5)

    def test_calculates_a_player_average_without_requiring_the_team_in_question(self) -> None:
        service = PlayerOpportunityService(
            discovery=PlayerDiscoveryService(FakePlayerSearch()),
            individual_statistics=FakeIndividualStatistics(),
        )

        result = service.evaluate_statistic(
            "Jude Bellingham tem media de quantos chutes no gol?"
        )

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.player, "Jude Bellingham")
        self.assertEqual(result.team, "Real Madrid")
        self.assertEqual(result.market, "chutes no alvo")
        self.assertEqual(result.average_metric, 0.8)
        self.assertIn("média de 0.80 chutes no alvo", result.answer)
