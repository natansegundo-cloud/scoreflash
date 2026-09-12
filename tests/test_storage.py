from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scoreflash.errors import TeamNotFoundError
from scoreflash.models import Team
from scoreflash.storage.sqlite import QueryCache, TeamIndex


class StorageTests(unittest.TestCase):
    def test_resolves_accent_and_alias(self) -> None:
        with TemporaryDirectory() as directory:
            index = TeamIndex(Path(directory) / "index.sqlite3")
            try:
                index.upsert(Team("flashscore", "abc123", "Athletico-PR", "Brasil"), ("CAP", "Athletico"))
                resolved = index.resolve("flashscore", "athlético pr")
                self.assertEqual(resolved.external_id, "abc123")
                self.assertEqual(index.resolve("flashscore", "cap").name, "Athletico-PR")
                with self.assertRaises(TeamNotFoundError):
                    index.resolve("flashscore", "Coritiba")
            finally:
                index.close()

    def test_cache_expires(self) -> None:
        with TemporaryDirectory() as directory:
            cache = QueryCache(Path(directory) / "cache.sqlite3")
            try:
                cache.put("query", {"answer": 16}, timedelta(minutes=1))
                self.assertEqual(cache.get("query"), {"answer": 16})
                cache.put("expired", {"answer": 0}, timedelta(seconds=-1))
                self.assertIsNone(cache.get("expired"))
            finally:
                cache.close()
