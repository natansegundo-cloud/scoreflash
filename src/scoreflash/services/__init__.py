"""Casos de uso e regras de cálculo."""

from .statistics import calculate_average
from .discovery import TeamDiscoveryService
from .insights import build_team_insight

__all__ = ["build_team_insight", "calculate_average", "TeamDiscoveryService"]
