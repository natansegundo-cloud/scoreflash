"""Interpretação estruturada via Groq, isolada do restante da aplicação."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..errors import LLMUnavailableError, QuestionInterpretationError
from ..models import Venue


@dataclass(frozen=True, slots=True)
class QuestionIntent:
    team_name: str
    metric: str
    games: int
    venue: Venue
    competition_name: str = ""
    opponent_name: str = ""
    kind: str = "team_statistic"


class GroqQuestionInterpreter:
    ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def parse(self, question: str, known_teams: Sequence[str]) -> QuestionIntent:
        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extraia uma consulta de estatística de futebol em português. "
                        "Responda somente JSON com team_name, opponent_name, kind, metric, games, venue e competition_name. "
                        "kind deve ser team_statistic ou head_to_head. Em head_to_head, team_name e a equipe principal e opponent_name e a outra equipe. "
                        "Quando uma equipe for mandante ou visitante, ela deve ser team_name. "
                        "venue deve ser any, home ou away. games deve ser inteiro de 1 a 20. "
                        "Extraia o nome da equipe citado pela pessoa mesmo que ela ainda não exista "
                        "no índice local. A lista serve apenas como referência de apelidos já conhecidos. "
                        f"Apelidos conhecidos: {', '.join(known_teams)}."
                    ),
                },
                {"role": "user", "content": question},
            ],
        }
        request = Request(
            self.ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:  # noqa: S310 - endpoint constante.
                body = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise LLMUnavailableError("A Groq não respondeu à interpretação da pergunta.") from error

        try:
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            games = int(parsed["games"])
            venue = Venue(parsed["venue"])
            team_name = str(parsed["team_name"]).strip()
            metric = str(parsed["metric"]).strip()
            competition_name = str(parsed.get("competition_name", "")).strip()
            opponent_name = str(parsed.get("opponent_name", "")).strip()
            kind = str(parsed.get("kind", "team_statistic")).strip()
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise QuestionInterpretationError("A Groq devolveu uma interpretação inválida.") from error
        if kind not in {"team_statistic", "head_to_head"}:
            raise QuestionInterpretationError("A Groq devolveu um tipo de consulta invalido.")
        if kind == "head_to_head" and not opponent_name:
            raise QuestionInterpretationError("A pergunta de confronto precisa informar as duas equipes.")
        if not metric or not 1 <= games <= 20:
            raise QuestionInterpretationError("A pergunta precisa informar uma estatística e período válidos.")
        return QuestionIntent(
            team_name=team_name,
            metric=metric,
            games=games,
            venue=venue,
            competition_name=competition_name,
            opponent_name=opponent_name,
            kind=kind,
        )
