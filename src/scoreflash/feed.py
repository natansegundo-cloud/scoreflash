"""Parser tolerante para o formato delimitado usado pelos feeds observados.

O formato não é JSON: campos são separados por ``¬`` e chave/valor por ``÷``.
Há chaves repetidas e grupos marcados por ``~``; por isso o parser preserva a
ordem e nunca transforma cegamente tudo em ``dict``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import FeedParseError

FIELD_SEPARATOR = "¬"
KEY_VALUE_SEPARATOR = "÷"
GROUP_MARKER = "~"


@dataclass(frozen=True, slots=True)
class FeedField:
    code: str
    value: str
    group: int


@dataclass(frozen=True, slots=True)
class FlashscoreFeed:
    raw: str
    fields: tuple[FeedField, ...]

    def values(self, code: str) -> tuple[str, ...]:
        """Retorna todas as ocorrências de uma chave, na ordem original."""
        return tuple(field.value for field in self.fields if field.code == code)

    def first(self, code: str, default: str | None = None) -> str | None:
        """Retorna a primeira ocorrência de uma chave."""
        return next(iter(self.values(code)), default)

    def group_fields(self, group: int) -> tuple[FeedField, ...]:
        return tuple(field for field in self.fields if field.group == group)


def parse_flashscore_feed(payload: str) -> FlashscoreFeed:
    """Lê um feed bruto sem atribuir significado aos seus códigos internos."""
    if not isinstance(payload, str) or not payload.strip():
        raise FeedParseError("O feed está vazio ou não é texto.")

    fields: list[FeedField] = []
    group = 0
    for raw_token in payload.split(FIELD_SEPARATOR):
        token = raw_token
        while token.startswith(GROUP_MARKER):
            group += 1
            token = token[1:]

        if not token:
            continue
        if KEY_VALUE_SEPARATOR not in token:
            # Alguns feeds incluem sentinelas sem chave; preservá-las como
            # texto seria enganoso, então a aplicação apenas as ignora.
            continue

        code, value = token.split(KEY_VALUE_SEPARATOR, maxsplit=1)
        if not code:
            raise FeedParseError("Foi encontrado um campo sem código.")
        fields.append(FeedField(code=code, value=value, group=group))

    if not fields:
        raise FeedParseError("Não foi encontrado nenhum campo no feed.")
    return FlashscoreFeed(raw=payload, fields=tuple(fields))
