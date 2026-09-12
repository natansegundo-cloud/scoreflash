"""Ponto de entrada da API para a Vercel."""

from __future__ import annotations

import sys
from pathlib import Path


source_directory = Path(__file__).parent / "src"
if str(source_directory) not in sys.path:
    sys.path.insert(0, str(source_directory))

from scoreflash.api import app
