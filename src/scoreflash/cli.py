"""Interface de terminal para validar o núcleo antes de expor uma API/bot."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from .config import Settings
from .errors import ScoreFlashError
from .models import Match, StatisticQuery, Team, Venue
from .providers.demo import InMemoryMatchProvider
from .providers.flashscore import FlashscoreClient, FlashscoreFeedKind
from .providers.history import FlashscoreHistoryProvider
from .services.narration import narrate_average
from .services.statistics import calculate_average


def _demo_matches() -> tuple[Team, tuple[Match, ...]]:
    flamengo = Team(provider="demo", external_id="flamengo", name="Flamengo", country="Brasil")
    opponent = Team(provider="demo", external_id="opponent", name="Adversário", country="Brasil")
    home_values = (18, 14, 16, 17, 15)
    matches = tuple(
        Match(
            external_id=f"demo-{index}",
            kickoff=datetime(2026, 9, 11 - index, tzinfo=UTC),
            home_team=flamengo,
            away_team=opponent,
            finished=True,
            statistics={"total_de_finalizacoes": (value, 8.0)},
        )
        for index, value in enumerate(home_values, start=1)
    )
    return flamengo, matches


def _run_demo() -> int:
    team, matches = _demo_matches()
    provider = InMemoryMatchProvider(matches)
    query = StatisticQuery(team=team, metric="finalizações", games=5, venue=Venue.HOME)
    result = calculate_average(query, provider.recent_matches(team, limit=20))
    print(narrate_average(result))
    return 0


def _fetch_feed(args: argparse.Namespace) -> int:
    settings = Settings.from_environ()
    client = FlashscoreClient(settings.flashscore_signature)
    retrieved = client.fetch_event_feed(
        args.event_id,
        FlashscoreFeedKind(args.kind),
        sport_id=args.sport_id,
    )
    report = {
        "url": retrieved.url,
        "kind": retrieved.kind,
        "fields": [
            {"code": field.code, "value": field.value, "group": field.group}
            for field in retrieved.feed.fields
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _fetch_statistics(args: argparse.Namespace) -> int:
    settings = Settings.from_environ()
    client = FlashscoreClient(settings.flashscore_signature)
    retrieved = client.fetch_statistics(args.event_id, sport_id=args.sport_id)
    report = {
        "url": retrieved.retrieved_feed.url,
        "statistics": [
            {
                "period": statistic.period,
                "section": statistic.section,
                "metric": statistic.metric,
                "home": statistic.home_value,
                "away": statistic.away_value,
                "unit": statistic.unit,
            }
            for statistic in retrieved.statistics
            if statistic.period == "Jogo"
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _team_average(args: argparse.Namespace) -> int:
    settings = Settings.from_environ()
    team = Team(
        provider="flashscore",
        external_id=args.team_id,
        name=args.team_name,
        country=args.country,
    )
    venue = Venue(args.venue)
    client = FlashscoreClient(settings.flashscore_signature)
    provider = FlashscoreHistoryProvider(
        client,
        team_slug=args.team_slug,
        country_id=args.country_id,
    )
    matches = provider.recent_matches_for_venue(team, args.games, venue)
    query = StatisticQuery(team=team, metric=args.metric, games=args.games, venue=venue)
    print(narrate_average(calculate_average(query, matches)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scoreflash")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Executa uma consulta com dados determinísticos.")

    feed = commands.add_parser("fetch-feed", help="Consulta um feed FlashScore já validado.")
    feed.add_argument("event_id", help="Identificador da partida, como Ghn7iaNE.")
    feed.add_argument(
        "--kind",
        choices=[
            kind.value
            for kind in FlashscoreFeedKind
            if kind is not FlashscoreFeedKind.PARTICIPANT_RESULTS
        ],
        default=FlashscoreFeedKind.METADATA.value,
    )
    feed.add_argument("--sport-id", type=int, default=1)

    statistics = commands.add_parser(
        "fetch-statistics",
        help="Consulta e estrutura as estatísticas de um jogo.",
    )
    statistics.add_argument("event_id", help="Identificador da partida, como pWui9o1n.")
    statistics.add_argument("--sport-id", type=int, default=1)

    average = commands.add_parser(
        "team-average",
        help="Calcula a média real de uma métrica nos jogos recentes de uma equipe.",
    )
    average.add_argument("team_id", help="ID FlashScore da equipe, como 6gMiRHVj.")
    average.add_argument("team_slug", help="Slug público da equipe, como newells-old-boys.")
    average.add_argument("team_name", help="Nome para a resposta, entre aspas se necessário.")
    average.add_argument("metric", help="Ex.: finalizações, escanteios, posse de bola.")
    average.add_argument("--games", type=int, default=5)
    average.add_argument("--venue", choices=[venue.value for venue in Venue], default=Venue.ANY.value)
    average.add_argument("--country", default=None)
    average.add_argument(
        "--country-id",
        type=int,
        default=None,
        help="Opcional; habilita paginação histórica se o bloco inicial não bastar.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "demo":
            return _run_demo()
        if args.command == "fetch-feed":
            return _fetch_feed(args)
        if args.command == "fetch-statistics":
            return _fetch_statistics(args)
        if args.command == "team-average":
            return _team_average(args)
    except ScoreFlashError as error:
        print(f"Erro: {error}")
        return 2
    raise AssertionError(f"Comando não tratado: {args.command}")
