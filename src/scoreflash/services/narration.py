"""Resposta inicial determinística; uma LLM pode substituí-la depois."""

from __future__ import annotations

from ..models import StatisticResult, StatisticUnit, Venue


def narrate_average(result: StatisticResult) -> str:
    query = result.query
    venue = {
        Venue.ANY: "",
        Venue.HOME: " em casa",
        Venue.AWAY: " fora de casa",
    }[query.venue]
    metric = query.metric.replace("_", " ")
    observed_games = len(result.matches_used)
    games_word = "jogo" if observed_games == 1 else "jogos"
    average = f"{result.average:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    measure = (
        f"{average}% de {metric}"
        if result.unit is StatisticUnit.PERCENTAGE
        else f"{average} {metric}"
    )
    competition = f" pela {query.competition_name}" if query.competition_name else ""
    requested = "" if observed_games == query.games else " disponíveis"
    return (
        f"Nos últimos {observed_games} {games_word}{requested}{venue}{competition}, "
        f"{query.team.name} teve média de {measure} por partida."
    )
