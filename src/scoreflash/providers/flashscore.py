"""Cliente de baixa escala para feeds observados do FlashScore.

Este módulo não tenta adivinhar endpoints de estatísticas. Cada novo feed deve
ser capturado e validado antes de virar uma capacidade pública do provedor.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..errors import ProviderAccessError, ProviderAuthenticationError
from ..feed import FlashscoreFeed, parse_flashscore_feed
from ..models import StatisticUnit
from ..normalization import normalize_text

Transport = Callable[[str, Mapping[str, str], float], str]


class FlashscoreFeedKind(StrEnum):
    METADATA = "metadata"
    SUPPLEMENTARY = "supplementary"
    BROADCASTS = "broadcasts"
    STATISTICS = "statistics"
    PARTICIPANT_RESULTS = "participant_results"


@dataclass(frozen=True, slots=True)
class RetrievedFeed:
    kind: FlashscoreFeedKind
    url: str
    feed: FlashscoreFeed


@dataclass(frozen=True, slots=True)
class FlashscoreStatistic:
    """Uma linha de estatística comprovadamente mapeada do feed ``df_st``."""

    period: str
    section: str
    source_id: str
    label: str
    metric: str
    home_value: float
    away_value: float
    unit: StatisticUnit


@dataclass(frozen=True, slots=True)
class RetrievedStatistics:
    retrieved_feed: RetrievedFeed
    statistics: tuple[FlashscoreStatistic, ...]


@dataclass(frozen=True, slots=True)
class RetrievedParticipantResults:
    retrieved_feed: RetrievedFeed
    matches: tuple["Match", ...]


_NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_INITIAL_FEED_RE = re.compile(
    r'cjs\.initialFeeds\["(?P<name>[^"]+)"\]\s*=\s*\{\s*data:\s*`(?P<data>.*?)`\s*,',
    flags=re.DOTALL,
)
_FEED_SIGNATURE_RE = re.compile(r'"feed_sign"\s*:\s*"(?P<value>[A-Za-z0-9_-]{4,128})"')


def _parse_statistic_value(raw_value: str) -> float | None:
    """Extrai o valor principal de ``54%`` ou ``80% (276/347)``."""
    match = _NUMBER_RE.search(raw_value)
    if match is None:
        return None
    return float(match.group(0).replace(",", "."))


def parse_statistics_feed(feed: FlashscoreFeed) -> tuple[FlashscoreStatistic, ...]:
    """Converte as chaves já verificadas de ``df_st`` em linhas tipadas.

    ``SE`` marca período, ``SF`` uma seção, ``SD`` o código da métrica, ``SG``
    o rótulo e ``SH``/``SI`` os valores de mandante/visitante. Estatísticas de
    primeiro e segundo tempo continuam disponíveis, mas a camada de cálculo
    deve selecionar ``period == 'Jogo'`` para responder perguntas por partida.
    """
    period = ""
    section = ""
    statistics: list[FlashscoreStatistic] = []
    groups = sorted({field.group for field in feed.fields})

    for group in groups:
        fields = feed.group_fields(group)
        by_code = {field.code: field.value for field in fields}
        if "SE" in by_code:
            period = by_code["SE"]
        if "SF" in by_code:
            section = by_code["SF"]
        if not {"SD", "SG", "SH", "SI"}.issubset(by_code):
            continue

        home_raw, away_raw = by_code["SH"], by_code["SI"]
        home_value = _parse_statistic_value(home_raw)
        away_value = _parse_statistic_value(away_raw)
        if home_value is None or away_value is None:
            continue
        label = by_code["SG"]
        statistics.append(
            FlashscoreStatistic(
                period=period,
                section=section,
                source_id=by_code["SD"],
                label=label,
                metric=normalize_text(label).replace(" ", "_"),
                home_value=home_value,
                away_value=away_value,
                unit=(
                    StatisticUnit.PERCENTAGE
                    if "%" in home_raw or "%" in away_raw
                    else StatisticUnit.NUMBER
                ),
            )
        )
    return tuple(statistics)


def _parse_score(value: str | None) -> float | None:
    if value is None or not re.fullmatch(r"-?\d+", value):
        return None
    return float(value)


def parse_participant_results_feed(feed: FlashscoreFeed) -> tuple["Match", ...]:
    """Converte o feed ``pr_`` de resultados em partidas do domínio.

    Campos validados: ``AA`` (evento), ``AD`` (data Unix), ``AE``/``PX``
    (mandante), ``AF``/``PY`` (visitante), ``AG``/``AH`` (placar final) e
    ``AB`` (estado). A competição e o país ficam em blocos anteriores,
    identificados por ``ZA`` e ``ZY``.
    """
    # Import tardio evita uma dependência circular ao expor o cliente no pacote.
    from ..models import Match, Team

    competition_name: str | None = None
    country: str | None = None
    country_id: int | None = None
    matches: list[Match] = []
    for group in sorted({field.group for field in feed.fields}):
        fields = feed.group_fields(group)
        by_code = {field.code: field.value for field in fields}
        if "ZA" in by_code:
            competition_name = by_code["ZA"]
            country = by_code.get("ZY", country)
            try:
                country_id = int(by_code["ZB"])
            except (KeyError, ValueError):
                pass
        if "AA" not in by_code:
            continue
        required = {"AD", "AE", "AF", "PX", "PY"}
        if not required.issubset(by_code):
            continue
        try:
            kickoff = datetime.fromtimestamp(int(by_code["AD"]), tz=UTC)
        except ValueError:
            continue

        matches.append(
            Match(
                external_id=by_code["AA"],
                kickoff=kickoff,
                home_team=Team(
                    provider="flashscore",
                    external_id=by_code["PX"],
                    name=by_code["AE"],
                    country=country,
                    participant_slug=by_code.get("WU"),
                    country_id=country_id,
                ),
                away_team=Team(
                    provider="flashscore",
                    external_id=by_code["PY"],
                    name=by_code["AF"],
                    country=country,
                    participant_slug=by_code.get("WV"),
                    country_id=country_id,
                ),
                # No feed p/pr observado, AB=3 representa partidas encerradas.
                finished=by_code.get("AB") == "3",
                statistics={
                    "goals": (_parse_score(by_code.get("AG")), _parse_score(by_code.get("AH")))
                }
                if _parse_score(by_code.get("AG")) is not None
                and _parse_score(by_code.get("AH")) is not None
                else {},
                competition_name=competition_name,
            )
        )
    return tuple(matches)


def extract_initial_feed(html: str, feed_name: str) -> str:
    """Extrai, sem executar JavaScript, um feed pré-carregado no HTML público."""
    for match in _INITIAL_FEED_RE.finditer(html):
        if match.group("name") != feed_name:
            continue
        payload = match.group("data")
        # Arquivos copiados de algumas ferramentas de DevTools podem chegar
        # com UTF-8 interpretado como latin-1. A correção é condicional para
        # não alterar respostas HTTP já decodificadas corretamente.
        if "Ã·" in payload or "Â¬" in payload:
            try:
                payload = payload.encode("latin-1").decode("utf-8")
            except UnicodeError:
                pass
        return payload
    raise ProviderAccessError(
        f"O HTML não contém o feed inicial {feed_name!r}. "
        "A estrutura da página pode ter mudado."
    )


def extract_feed_signature(html: str) -> str:
    """Lê a assinatura publicada na configuração da página do FlashScore."""
    match = _FEED_SIGNATURE_RE.search(html)
    if match is None:
        raise ProviderAccessError(
            "Não foi possível preparar a consulta automática no FlashScore. "
            "A configuração pública da página mudou."
        )
    return match.group("value")


def merge_match_statistics(
    match: "Match", statistics: tuple[FlashscoreStatistic, ...]
) -> "Match":
    """Anexa ao jogo apenas as estatísticas consolidadas do período inteiro."""
    values = dict(match.statistics)
    units = dict(match.statistic_units)
    # A seção Destaques contém as métricas mais comuns; mantê-la como primeira
    # escolha evita duplicidade de Total de finalizações, escanteios etc.
    for statistic in statistics:
        if statistic.period != "Jogo":
            continue
        if statistic.metric in values:
            continue
        values[statistic.metric] = (statistic.home_value, statistic.away_value)
        units[statistic.metric] = statistic.unit
    return replace(match, statistics=values, statistic_units=units)


def _default_transport(url: str, headers: Mapping[str, str], timeout: float) -> str:
    request = Request(url, headers=dict(headers))
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is validated below.
            return response.read().decode("utf-8")
    except HTTPError as error:
        if error.code in {401, 403}:
            raise ProviderAuthenticationError(
                "O FlashScore recusou a chamada. Atualize a assinatura x-fsign "
                "capturada no navegador."
            ) from error
        raise ProviderAccessError(f"O FlashScore respondeu HTTP {error.code}.") from error
    except URLError as error:
        raise ProviderAccessError("Não foi possível alcançar o FlashScore.") from error


class FlashscoreClient:
    BASE_URL = "https://global.flashscore.ninja"
    PROJECT_ID = "401"
    PROJECT_TYPE_ID = "1"
    DEFAULT_REFERER = "https://www.flashscore.com.br/"
    SIGNATURE_SOURCE_URL = DEFAULT_REFERER
    EVENT_PAGE_URL = "https://www.flashscore.com.br/jogo/{event_id}/"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    )
    PAGE_HEADERS = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
            "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(
        self,
        signature: str = "",
        *,
        timeout_seconds: float = 12.0,
        transport: Transport = _default_transport,
    ) -> None:
        self._signature = signature.strip()
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def fetch_event_feed(
        self,
        event_id: str,
        kind: FlashscoreFeedKind,
        *,
        sport_id: int = 1,
    ) -> RetrievedFeed:
        """Baixa um dos feeds já validados para uma partida específica."""
        if kind is FlashscoreFeedKind.PARTICIPANT_RESULTS:
            raise ValueError("Use fetch_participant_results para o feed de histórico.")
        if not re.fullmatch(r"[A-Za-z0-9]+", event_id):
            raise ValueError("event_id deve conter apenas letras e números.")
        if sport_id < 1:
            raise ValueError("sport_id deve ser positivo.")
        if not self._signature:
            self._resolve_signature(self._event_page_url(event_id))

        feed_name = self._feed_name(event_id, kind, sport_id)
        return self._fetch_feed_name(feed_name, kind)

    def fetch_participant_results(
        self,
        participant_id: str,
        country_id: int,
        *,
        page: int = 1,
        sport_id: int = 1,
        timezone_hour: int = -3,
        language: str = "pt-br",
    ) -> RetrievedParticipantResults:
        """Busca uma página histórica de resultados de uma equipe.

        O cursor ``page`` segue a composição usada pelo cliente oficial. A
        camada que o chama seleciona somente os N jogos de que precisa antes de
        baixar qualquer estatística individual.
        """
        if not re.fullmatch(r"[A-Za-z0-9]+", participant_id):
            raise ValueError("participant_id deve conter apenas letras e números.")
        if country_id < 1 or page < 1 or sport_id < 1:
            raise ValueError("country_id, page e sport_id devem ser positivos.")
        if not re.fullmatch(r"[a-z]{2}-[a-z]{2}", language):
            raise ValueError("language deve seguir o formato pt-br.")
        feed_name = "_".join(
            (
                "pr",
                str(sport_id),
                str(country_id),
                participant_id,
                str(page),
                str(timezone_hour),
                language,
                self.PROJECT_TYPE_ID,
            )
        )
        retrieved_feed = self._fetch_feed_name(feed_name, FlashscoreFeedKind.PARTICIPANT_RESULTS)
        return RetrievedParticipantResults(
            retrieved_feed=retrieved_feed,
            matches=parse_participant_results_feed(retrieved_feed.feed),
        )

    def fetch_initial_participant_results(
        self,
        participant_id: str,
        participant_slug: str,
    ) -> RetrievedParticipantResults:
        """Lê os resultados recentes pré-carregados na página pública da equipe.

        Não usa cookies, não controla navegador e não executa JavaScript. A
        resposta já contém o mesmo feed delimitado que o cliente do site usa.
        """
        if not re.fullmatch(r"[A-Za-z0-9]+", participant_id):
            raise ValueError("participant_id deve conter apenas letras e números.")
        if not re.fullmatch(r"[a-z0-9-]+", participant_slug):
            raise ValueError("participant_slug contém caracteres inválidos.")
        url = (
            f"https://www.flashscore.com.br/equipe/{participant_slug}/"
            f"{participant_id}/resultados/"
        )
        headers = {"User-Agent": self.DEFAULT_USER_AGENT, **self.PAGE_HEADERS}
        html = self._transport(url, headers, self._timeout_seconds)
        if not self._signature:
            self._signature = extract_feed_signature(html)
        payload = extract_initial_feed(html, "results")
        feed = parse_flashscore_feed(payload)
        retrieved_feed = RetrievedFeed(
            kind=FlashscoreFeedKind.PARTICIPANT_RESULTS,
            url=url,
            feed=feed,
        )
        return RetrievedParticipantResults(
            retrieved_feed=retrieved_feed,
            matches=parse_participant_results_feed(feed),
        )

    def hydrate_match_statistics(self, match: "Match") -> "Match":
        retrieved = self.fetch_statistics(match.external_id)
        return merge_match_statistics(match, retrieved.statistics)

    def fetch_initial_participant_fixtures(
        self,
        participant_id: str,
        participant_slug: str,
    ) -> RetrievedParticipantResults:
        """Lê os próximos jogos pré-carregados no calendário público da equipe."""
        if not re.fullmatch(r"[A-Za-z0-9]+", participant_id):
            raise ValueError("participant_id deve conter apenas letras e números.")
        if not re.fullmatch(r"[a-z0-9-]+", participant_slug):
            raise ValueError("participant_slug contém caracteres inválidos.")
        url = (
            f"https://www.flashscore.com.br/equipe/{participant_slug}/"
            f"{participant_id}/calendario/"
        )
        headers = {"User-Agent": self.DEFAULT_USER_AGENT, **self.PAGE_HEADERS}
        html = self._transport(url, headers, self._timeout_seconds)
        if not self._signature:
            self._signature = extract_feed_signature(html)
        payload = extract_initial_feed(html, "fixtures")
        feed = parse_flashscore_feed(payload)
        retrieved_feed = RetrievedFeed(
            kind=FlashscoreFeedKind.PARTICIPANT_RESULTS,
            url=url,
            feed=feed,
        )
        return RetrievedParticipantResults(
            retrieved_feed=retrieved_feed,
            matches=parse_participant_results_feed(feed),
        )

    def _fetch_feed_name(self, feed_name: str, kind: FlashscoreFeedKind) -> RetrievedFeed:
        url = f"{self.BASE_URL}/{self.PROJECT_ID}/x/feed/{feed_name}"
        payload = self._fetch_with_signature_retry(url)
        return RetrievedFeed(kind=kind, url=url, feed=parse_flashscore_feed(payload))

    def _fetch_with_signature_retry(self, url: str) -> str:
        for attempt in range(2):
            signature = self._signature or self._resolve_signature()
            headers = {
                "Accept": "text/plain, */*",
                "Referer": self.DEFAULT_REFERER,
                "User-Agent": self.DEFAULT_USER_AGENT,
                "x-fsign": signature,
            }
            try:
                return self._transport(url, headers, self._timeout_seconds)
            except ProviderAuthenticationError:
                if attempt:
                    raise ProviderAuthenticationError(
                        "O FlashScore recusou a consulta automática. Tente novamente mais tarde."
                    ) from None
                self._signature = ""
        raise AssertionError("A tentativa de renovar a assinatura deveria ter retornado ou falhado.")

    def _resolve_signature(self, source_url: str | None = None) -> str:
        headers = {"User-Agent": self.DEFAULT_USER_AGENT, **self.PAGE_HEADERS}
        html = self._transport(
            source_url or self.SIGNATURE_SOURCE_URL,
            headers,
            self._timeout_seconds,
        )
        self._signature = extract_feed_signature(html)
        return self._signature

    def fetch_statistics(self, event_id: str, *, sport_id: int = 1) -> RetrievedStatistics:
        """Baixa e estrutura as estatísticas de uma partida específica."""
        retrieved_feed = self.fetch_event_feed(
            event_id,
            FlashscoreFeedKind.STATISTICS,
            sport_id=sport_id,
        )
        return RetrievedStatistics(
            retrieved_feed=retrieved_feed,
            statistics=parse_statistics_feed(retrieved_feed.feed),
        )

    @staticmethod
    def _feed_name(event_id: str, kind: FlashscoreFeedKind, sport_id: int) -> str:
        prefix = {
            FlashscoreFeedKind.METADATA: "dc",
            FlashscoreFeedKind.SUPPLEMENTARY: "df_sui",
            FlashscoreFeedKind.BROADCASTS: "df_dos",
            FlashscoreFeedKind.STATISTICS: "df_st",
        }[kind]
        suffix = "_" if kind is FlashscoreFeedKind.BROADCASTS else ""
        return f"{prefix}_{sport_id}_{event_id}{suffix}"

    @classmethod
    def _event_page_url(cls, event_id: str) -> str:
        return cls.EVENT_PAGE_URL.format(event_id=event_id)
