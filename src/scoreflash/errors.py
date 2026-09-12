"""Exceções explícitas para que adaptadores não vazem detalhes ao usuário."""


class ScoreFlashError(Exception):
    """Erro base da aplicação."""


class FeedParseError(ScoreFlashError):
    """O feed não segue o formato delimitado esperado."""


class ProviderAccessError(ScoreFlashError):
    """A fonte externa não pôde ser acessada."""


class ProviderAuthenticationError(ProviderAccessError):
    """A assinatura/cabeçalho exigido pela fonte está ausente ou inválido."""


class UnsupportedProviderCapability(ScoreFlashError):
    """O provedor ainda não tem um endpoint validado para a operação."""


class TeamNotFoundError(ScoreFlashError):
    """O nome informado não pôde ser resolvido no índice local."""


class PlayerNotFoundError(ScoreFlashError):
    """O atleta informado não pôde ser encontrado ou validado."""


class InsufficientDataError(ScoreFlashError):
    """Não existem partidas suficientes para calcular a consulta."""


class QuestionInterpretationError(ScoreFlashError):
    """A pergunta não contém parâmetros suficientes para uma consulta segura."""


class LLMUnavailableError(ScoreFlashError):
    """O provedor de linguagem não pôde atender à solicitação."""


class TeamConfigurationError(ScoreFlashError):
    """O time foi localizado, mas ainda não tem metadados para busca ao vivo."""
