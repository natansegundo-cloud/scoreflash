"""Configuração carregada do ambiente, sem segredos no repositório."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_local_env() -> None:
    """Carrega um .env simples para a experiência local, sem dependência externa."""
    environment_file = Path(".env")
    if not environment_file.is_file():
        return
    for raw_line in environment_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _environment_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _allowed_origins() -> tuple[str, ...]:
    configured = os.getenv("SCOREFLASH_ALLOWED_ORIGINS", "")
    origins = tuple(origin.strip() for origin in configured.split(",") if origin.strip())
    if origins:
        return origins
    if os.getenv("VERCEL"):
        # O endpoint é público e não usa cookies. Isso permite que o projeto
        # web e a API sejam publicados separadamente na Vercel no MVP.
        return ("*",)
    return ("http://localhost:5173", "http://127.0.0.1:5173")


def save_api_football_key(api_key: str, environment_file: Path | None = None) -> None:
    """Salva somente a chave local da API-Football, sem devolvê-la à interface."""
    clean_key = api_key.strip()
    if not 12 <= len(clean_key) <= 200:
        raise ValueError("A chave da API-Football parece incompleta.")
    target = environment_file or Path(".env")
    lines = target.read_text(encoding="utf-8").splitlines() if target.is_file() else []
    replacement = f"API_FOOTBALL_API_KEY={clean_key}"
    saved = False
    updated_lines: list[str] = []
    for line in lines:
        if line.strip().startswith("API_FOOTBALL_API_KEY="):
            if not saved:
                updated_lines.append(replacement)
                saved = True
            continue
        updated_lines.append(line)
    if not saved:
        updated_lines.extend(("", "# Chave local para estatísticas individuais verificadas.", replacement))
    target.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")


@dataclass(frozen=True, slots=True)
class Settings:
    flashscore_signature: str
    data_dir: Path
    groq_api_key: str | None = None
    groq_model: str | None = None
    api_football_api_key: str | None = None
    allowed_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    allow_local_key_setup: bool = True

    @classmethod
    def from_environ(cls) -> "Settings":
        _load_local_env()
        on_vercel = bool(os.getenv("VERCEL"))
        data_directory = os.getenv("SCOREFLASH_DATA_DIR") or ("/tmp/scoreflash" if on_vercel else "data")
        return cls(
            flashscore_signature=os.getenv("SCOREFLASH_FLASHSCORE_SIGNATURE", "").strip(),
            data_dir=Path(data_directory),
            groq_api_key=os.getenv("GROQ_API_KEY") or None,
            groq_model=os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile",
            api_football_api_key=os.getenv("API_FOOTBALL_API_KEY") or None,
            allowed_origins=_allowed_origins(),
            allow_local_key_setup=_environment_flag("SCOREFLASH_ALLOW_LOCAL_KEY_SETUP", not on_vercel),
        )
