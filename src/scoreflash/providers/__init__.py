"""Adaptadores para fontes de partidas."""

from .base import MatchHistoryProvider
from .flashscore import (
    FlashscoreClient,
    FlashscoreFeedKind,
    extract_initial_feed,
    parse_statistics_feed,
)
from .history import FlashscoreHistoryProvider
from .search import FlashscoreSearchClient

__all__ = [
    "FlashscoreClient",
    "FlashscoreFeedKind",
    "FlashscoreHistoryProvider",
    "FlashscoreSearchClient",
    "extract_initial_feed",
    "MatchHistoryProvider",
    "parse_statistics_feed",
]
