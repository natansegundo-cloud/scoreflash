import json
import unittest

from scoreflash.models import Player
from scoreflash.providers.player import FlashscorePlayerClient, extract_json_assignment, parse_player_appearances


class PlayerProfileTests(unittest.TestCase):
    def test_extracts_only_the_json_assignment_from_the_page(self) -> None:
        html = (
            '<script>window.playerProfilePageEnvironment = {"lastMatchesData":{"lastMatches":[]}};</script>'
            '<script>window.otherEnvironment = {"unexpected":true};</script>'
        )

        payload = extract_json_assignment(html, "window.playerProfilePageEnvironment")

        self.assertEqual(payload["lastMatchesData"], {"lastMatches": []})

    def test_parses_minutes_rating_and_match_context(self) -> None:
        payload = {
            "lastMatchesData": {
                "lastMatches": [
                    {
                        "eventEncodedId": "Ab12Cd34",
                        "eventStartTime": "11.09.26",
                        "homeParticipantName": "Flamengo",
                        "awayParticipantName": "Palmeiras",
                        "tournamentTitle": "Brasileirão",
                        "rating": "7.4",
                        "stats": {"595": {"type": "minutes-played", "value": "83'"}},
                    }
                ]
            }
        }

        appearances = parse_player_appearances(payload)

        self.assertEqual(appearances[0].minutes, 83)
        self.assertEqual(appearances[0].rating, 7.4)
        self.assertEqual(appearances[0].home_team, "Flamengo")

    def test_fetches_a_public_profile_without_running_javascript(self) -> None:
        payload = json.dumps(
            {
                "lastMatchesData": {
                    "lastMatches": [
                        {
                            "eventEncodedId": "Ab12Cd34",
                            "eventStartTime": "11.09.26",
                            "homeParticipantName": "Flamengo",
                            "awayParticipantName": "Palmeiras",
                            "stats": {},
                        }
                    ]
                }
            }
        )
        player = Player("flashscore", "Sx6m4B4C", "Léo Ortiz", "leo-ortiz")
        client = FlashscorePlayerClient(
            transport=lambda *_: f"<script>window.playerProfilePageEnvironment = {payload};</script>"
        )

        profile = client.fetch_profile(player)

        self.assertEqual(profile.player.name, "Léo Ortiz")
        self.assertEqual(len(profile.appearances), 1)
