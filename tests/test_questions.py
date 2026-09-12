from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scoreflash.catalog import seed_initial_catalog
from scoreflash.config import Settings
from scoreflash.services.questions import QueryService, RuleBasedQuestionInterpreter
from scoreflash.storage.sqlite import QueryCache, TeamIndex


class QuestionInterpreterTests(unittest.TestCase):
    def test_interprets_known_team_home_venue_and_game_count(self) -> None:
        intent = RuleBasedQuestionInterpreter().parse(
            "Qual a média de finalizações do Newell's em casa nos últimos 5 jogos?",
            ("newells", "newell s old boys"),
        )

        self.assertEqual(intent.metric, "finalizações")
        self.assertEqual(intent.games, 5)
        self.assertEqual(intent.venue.value, "home")

    def test_recognizes_the_competition_in_the_question(self) -> None:
        intent = RuleBasedQuestionInterpreter().parse(
            "Qual a média de chutes do Brentford pela Premier League fora de casa?",
            ("brentford",),
        )

        self.assertEqual(intent.team_name, "brentford")
        self.assertEqual(intent.competition_name, "premier league")
        self.assertEqual(intent.venue.value, "away")

    def test_seeded_catalog_resolves_newells(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "scoreflash.sqlite3"
            teams = TeamIndex(path)
            cache = QueryCache(path)
            try:
                seed_initial_catalog(teams)
                service = QueryService(
                    Settings(flashscore_signature="test", data_dir=Path(directory)),
                    teams,
                    cache,
                )
                resolved = teams.resolve_mentioned("flashscore", "estatísticas do Newells")
                self.assertEqual(resolved.participant_slug, "newells-old-boys")
                self.assertIn("newells", teams.aliases("flashscore"))
                self.assertIsNotNone(service)
            finally:
                teams.close()
                cache.close()

    def test_keeps_metric_when_team_is_not_in_the_local_catalog(self) -> None:
        intent = RuleBasedQuestionInterpreter().parse(
            "Qual a média de finalizações do Flamengo nos últimos 5 jogos?",
            ("newells",),
        )

        self.assertEqual(intent.team_name, "")
        self.assertEqual(intent.metric, "finalizações")
        self.assertEqual(intent.games, 5)

    def test_recognizes_a_player_prop_recommendation(self) -> None:
        self.assertTrue(
            QueryService._is_player_opportunity_question(
                "O Léo Ortiz é uma boa ideia para finalizar no jogo de amanhã do Flamengo?"
            )
        )
        self.assertFalse(
            QueryService._is_player_opportunity_question(
                "Qual a média de finalizações do Flamengo nos últimos 5 jogos?"
            )
        )
        self.assertTrue(
            QueryService._is_player_opportunity_question(
                "O Léo Ortiz vale cartão amarelo amanhã pelo Flamengo?"
            )
        )
