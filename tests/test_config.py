from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scoreflash.config import save_api_football_key


class ConfigTests(unittest.TestCase):
    def test_saves_and_replaces_only_the_api_football_key_line(self) -> None:
        with TemporaryDirectory() as directory:
            environment_file = Path(directory) / ".env"
            environment_file.write_text("GROQ_MODEL=example\nAPI_FOOTBALL_API_KEY=old-key-value\n", encoding="utf-8")

            save_api_football_key("new-key-value-123", environment_file)

            lines = environment_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], "GROQ_MODEL=example")
            self.assertEqual(lines[1], "API_FOOTBALL_API_KEY=new-key-value-123")
            self.assertEqual(sum(line.startswith("API_FOOTBALL_API_KEY=") for line in lines), 1)
