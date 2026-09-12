"""Leituras humanas determinísticas para estatísticas de equipe."""

from __future__ import annotations

from ..models import StatisticResult, StatisticUnit
from .statistics import metric_key


def confidence_for_sample(games: int) -> str:
    if games >= 8:
        return "alta"
    if games >= 5:
        return "média"
    return "inicial"


def build_team_insight(result: StatisticResult) -> str:
    """Explica tendência recente sem extrapolar além da amostra observada."""
    query = result.query
    key = metric_key(query.metric)
    values = [match.team_value(query.team, key) for match in result.matches_used]
    observed = [value for value in values if value is not None]
    if len(observed) < 2:
        return "A leitura usa uma amostra curta; trate o número como referência inicial."

    split = max(1, len(observed) // 2)
    recent_average = sum(observed[:split]) / split
    earlier_values = observed[split:]
    earlier_average = sum(earlier_values) / len(earlier_values)
    if earlier_average == 0:
        trend = "não há base anterior suficiente para comparar a tendência"
    else:
        change = ((recent_average - earlier_average) / earlier_average) * 100
        if abs(change) < 12:
            trend = "o volume ficou relativamente estável dentro da amostra"
        elif change > 0:
            trend = f"os jogos mais recentes ficaram {change:.0f}% acima da parte anterior"
        else:
            trend = f"os jogos mais recentes ficaram {abs(change):.0f}% abaixo da parte anterior"

    formatted_average = f"{result.average:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    suffix = "%" if result.unit is StatisticUnit.PERCENTAGE else " por jogo"
    return (
        f"A leitura é baseada em {len(observed)} jogos: {formatted_average}{suffix}. "
        f"Dentro desse recorte, {trend}. Confiança {confidence_for_sample(len(observed))}."
    )
