"""Persistência local e leve do ScoreFlash."""

from .sqlite import QueryCache, TeamIndex

__all__ = ["QueryCache", "TeamIndex"]
