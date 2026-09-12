from pathlib import Path
import unittest

from scoreflash.feed import parse_flashscore_feed
from scoreflash.errors import ProviderAuthenticationError
from scoreflash.providers.flashscore import (
    FlashscoreClient,
    FlashscoreFeedKind,
    extract_feed_signature,
    extract_initial_feed,
    parse_participant_results_feed,
    parse_statistics_feed,
)


class FlashscoreClientTests(unittest.TestCase):
    def test_extracts_automatic_signature_from_public_page(self) -> None:
        html = '<script>window.environment={"config":{"app":{"feed_sign":"auto-signature"}}};</script>'

        self.assertEqual(extract_feed_signature(html), "auto-signature")

    def test_fetches_signature_automatically_when_not_configured(self) -> None:
        captured: list[tuple[str, dict[str, str]]] = []
        payload = (Path(__file__).parent / "fixtures" / "match_metadata.txt").read_text(encoding="utf-8")

        def transport(url: str, headers: dict[str, str], timeout: float) -> str:
            captured.append((url, headers))
            if url == FlashscoreClient._event_page_url("Ghn7iaNE"):
                return '<script>{"feed_sign":"automatic-signature"}</script>'
            return payload

        client = FlashscoreClient(transport=transport)
        client.fetch_event_feed("Ghn7iaNE", FlashscoreFeedKind.METADATA)

        self.assertEqual(captured[0][0], FlashscoreClient._event_page_url("Ghn7iaNE"))
        self.assertEqual(captured[1][1]["x-fsign"], "automatic-signature")

    def test_refreshes_automatic_signature_after_authentication_error(self) -> None:
        payload = (Path(__file__).parent / "fixtures" / "match_metadata.txt").read_text(encoding="utf-8")
        sent_signatures: list[str] = []

        def transport(url: str, headers: dict[str, str], timeout: float) -> str:
            if url == FlashscoreClient.SIGNATURE_SOURCE_URL:
                return '<script>{"feed_sign":"new-signature"}</script>'
            sent_signatures.append(headers["x-fsign"])
            if len(sent_signatures) == 1:
                raise ProviderAuthenticationError("expired")
            return payload

        client = FlashscoreClient("old-signature", transport=transport)
        client.fetch_event_feed("Ghn7iaNE", FlashscoreFeedKind.METADATA)

        self.assertEqual(sent_signatures, ["old-signature", "new-signature"])

    def test_builds_validated_metadata_request(self) -> None:
        captured: dict[str, object] = {}
        payload = (Path(__file__).parent / "fixtures" / "match_metadata.txt").read_text(encoding="utf-8")

        def transport(url: str, headers: dict[str, str], timeout: float) -> str:
            captured.update(url=url, headers=headers, timeout=timeout)
            return payload

        client = FlashscoreClient("current-signature", transport=transport)
        result = client.fetch_event_feed("Ghn7iaNE", FlashscoreFeedKind.METADATA)

        self.assertEqual(
            captured["url"],
            "https://global.flashscore.ninja/401/x/feed/dc_1_Ghn7iaNE",
        )
        self.assertEqual(captured["headers"]["x-fsign"], "current-signature")
        self.assertEqual(result.feed.first("QX"), "Fabio Salomao")

    def test_parses_validated_statistics_fields(self) -> None:
        payload = (Path(__file__).parent / "fixtures" / "match_statistics.txt").read_text(encoding="utf-8")
        statistics = parse_statistics_feed(parse_flashscore_feed(payload))

        shots = next(
            statistic
            for statistic in statistics
            if statistic.period == "Jogo" and statistic.metric == "total_de_finalizacoes"
        )
        possession = next(
            statistic
            for statistic in statistics
            if statistic.period == "Jogo" and statistic.metric == "posse_de_bola"
        )
        self.assertEqual((shots.home_value, shots.away_value), (13.0, 3.0))
        self.assertEqual(possession.unit.value, "percentage")

    def test_parses_participant_results_with_teams_and_score(self) -> None:
        payload = (Path(__file__).parent / "fixtures" / "participant_results.txt").read_text(encoding="utf-8")
        matches = parse_participant_results_feed(parse_flashscore_feed(payload))

        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].external_id, "r99VVrJs")
        self.assertEqual(matches[0].home_team.name, "Newell's Old Boys")
        self.assertEqual(matches[0].away_team.name, "Central Córdoba")
        self.assertEqual(matches[0].statistics["goals"], (1.0, 1.0))
        self.assertEqual(matches[1].away_team.name, "Newell's Old Boys")

    def test_builds_participant_results_feed(self) -> None:
        captured: dict[str, object] = {}
        payload = (Path(__file__).parent / "fixtures" / "participant_results.txt").read_text(encoding="utf-8")

        def transport(url: str, headers: dict[str, str], timeout: float) -> str:
            captured.update(url=url, headers=headers, timeout=timeout)
            return payload

        client = FlashscoreClient("current-signature", transport=transport)
        result = client.fetch_participant_results("6gMiRHVj", country_id=22)

        self.assertEqual(
            captured["url"],
            "https://global.flashscore.ninja/401/x/feed/pr_1_22_6gMiRHVj_1_-3_pt-br_1",
        )
        self.assertEqual(result.matches[0].external_id, "r99VVrJs")

    def test_extracts_results_feed_from_public_html(self) -> None:
        raw_feed = (Path(__file__).parent / "fixtures" / "participant_results.txt").read_text(encoding="utf-8")
        html = (
            "<script>if (!cjs.initialFeeds) { cjs.initialFeeds = []; }"
            f'cjs.initialFeeds["results"] = {{ data: `{raw_feed}`, allEventsCount: 2 }};'
            "</script>"
        )

        extracted = extract_initial_feed(html, "results")

        self.assertEqual(extracted, raw_feed)

    def test_extracts_fixtures_from_public_calendar_html(self) -> None:
        raw_feed = (Path(__file__).parent / "fixtures" / "participant_results.txt").read_text(encoding="utf-8")
        html = (
            '<script>{"feed_sign":"automatic-signature"}'
            f'cjs.initialFeeds["fixtures"] = {{ data: `{raw_feed}`, allEventsCount: 2 }};'
            "</script>"
        )
        client = FlashscoreClient(transport=lambda *_: html)

        retrieved = client.fetch_initial_participant_fixtures("6gMiRHVj", "newells-old-boys")

        self.assertEqual(len(retrieved.matches), 2)
        self.assertEqual(retrieved.matches[0].external_id, "r99VVrJs")
