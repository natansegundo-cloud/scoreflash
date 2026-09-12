from pathlib import Path
import unittest

from scoreflash.feed import parse_flashscore_feed


FIXTURES = Path(__file__).parent / "fixtures"


class FlashscoreFeedParserTests(unittest.TestCase):
    def test_preserves_fields_from_metadata_feed(self) -> None:
        feed = parse_flashscore_feed((FIXTURES / "match_metadata.txt").read_text(encoding="utf-8"))

        self.assertEqual(feed.first("DA"), "1")
        self.assertEqual(feed.first("QX"), "Fabio Salomao")
        self.assertEqual(feed.first("DD"), "1789171200")
        self.assertEqual(feed.first("missing"), None)

    def test_preserves_repeated_keys_and_groups(self) -> None:
        feed = parse_flashscore_feed((FIXTURES / "match_supplementary.txt").read_text(encoding="utf-8"))

        self.assertEqual(feed.values("MIT"), ("REF", "RCO", "RTY", "RCC", "VEN", "TWN", "CAP"))
        self.assertEqual(feed.values("MIV")[0], "Wagner do Nascimento")
        self.assertGreater(feed.group_fields(1).__len__(), 0)

    def test_rejects_empty_payload(self) -> None:
        with self.assertRaisesRegex(Exception, "vazio"):
            parse_flashscore_feed("")
