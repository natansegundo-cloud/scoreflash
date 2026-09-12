"""Cálculos de estatísticas puras, testáveis sem HTTP ou banco de dados."""

from __future__ import annotations

from collections.abc import Sequence

from ..errors import InsufficientDataError
from ..models import Match, StatisticQuery, StatisticResult
from ..normalization import normalize_text

_METRIC_ALIASES = {
    "gols": "goals",
    "gol": "goals",
    "finalizacoes": "total_de_finalizacoes",
    "chutes": "total_de_finalizacoes",
    "shots": "total_de_finalizacoes",
    "posse": "posse_de_bola",
    "posse_bola": "posse_de_bola",
    "amarelos": "cartoes_amarelos",
}


def metric_key(metric: str) -> str:
    normalized = normalize_text(metric).replace(" ", "_")
    return _METRIC_ALIASES.get(normalized, normalized)


def calculate_average(query: StatisticQuery, matches: Sequence[Match]) -> StatisticResult:
    """Calcula uma média usando o recorte solicitado.

    Partidas não encerradas, de outro mando, ou sem a métrica solicitada não
    contaminam o cálculo. Quando a fonte não registra a métrica em todas as
    partidas recentes, a resposta usa a amostra realmente disponível e a
    informa à pessoa. Sem nenhum dado, continua sendo erro explícito.
    """
    if query.games <= 0:
        raise ValueError("games deve ser maior que zero.")

    key = metric_key(query.metric)
    selected: list[Match] = []
    values: list[float] = []
    for match in sorted(matches, key=lambda item: item.kickoff, reverse=True):
        if not match.finished or match.venue_for(query.team) is None:
            continue
        if query.venue.value != "any" and match.venue_for(query.team) != query.venue:
            continue
        if query.competition_name:
            competition = normalize_text(match.competition_name or "")
            requested_competition = normalize_text(query.competition_name)
            if requested_competition not in competition:
                continue
        value = match.team_value(query.team, key)
        if value is None:
            continue
        selected.append(match)
        values.append(value)
        if len(selected) == query.games:
            break

    if not selected:
        raise InsufficientDataError(
            f"Não encontrei partidas com {key!r} para esse recorte. "
            "Tente ampliar o período, remover a liga ou trocar o mando."
        )

    return StatisticResult(
        query=query,
        average=sum(values) / len(values),
        matches_used=tuple(selected),
        unit=selected[0].statistic_unit(key),
    )
