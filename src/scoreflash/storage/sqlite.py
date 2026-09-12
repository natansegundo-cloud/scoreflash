"""SQLite para índice de nomes e cache de resultados de consulta."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any

from ..errors import TeamNotFoundError
from ..models import Team
from ..normalization import normalize_text


class _SqliteStore:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(database_path, check_same_thread=False, timeout=10)
        self._connection.row_factory = sqlite3.Row

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class TeamIndex(_SqliteStore):
    def __init__(self, database_path: Path) -> None:
        super().__init__(database_path)
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS teams (
                    id INTEGER PRIMARY KEY,
                    provider TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    country TEXT,
                    participant_slug TEXT,
                    country_id INTEGER,
                    UNIQUE(provider, external_id)
                );
                CREATE TABLE IF NOT EXISTS team_aliases (
                    provider TEXT NOT NULL,
                    normalized_alias TEXT NOT NULL,
                    team_id INTEGER NOT NULL REFERENCES teams(id),
                    UNIQUE(provider, normalized_alias)
                );
                """
            )
        self._ensure_team_columns()

    def _ensure_team_columns(self) -> None:
        """Migra instalações locais anteriores aos metadados de busca."""
        with self._lock:
            columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(teams)").fetchall()
            }
            if "participant_slug" not in columns:
                self._connection.execute("ALTER TABLE teams ADD COLUMN participant_slug TEXT")
            if "country_id" not in columns:
                self._connection.execute("ALTER TABLE teams ADD COLUMN country_id INTEGER")
            self._connection.commit()

    def upsert(self, team: Team, aliases: tuple[str, ...] = ()) -> None:
        with self._lock:
            cursor = self._connection.cursor()
            cursor.execute(
                """
                INSERT INTO teams(provider, external_id, name, country, participant_slug, country_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, external_id) DO UPDATE SET
                    name = excluded.name,
                    country = excluded.country,
                    participant_slug = excluded.participant_slug,
                    country_id = excluded.country_id
                """,
                (
                    team.provider,
                    team.external_id,
                    team.name,
                    team.country,
                    team.participant_slug,
                    team.country_id,
                ),
            )
            row = cursor.execute(
                "SELECT id FROM teams WHERE provider = ? AND external_id = ?",
                (team.provider, team.external_id),
            ).fetchone()
            assert row is not None
            for alias in {team.name, *aliases}:
                cursor.execute(
                    """
                    INSERT INTO team_aliases(provider, normalized_alias, team_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT(provider, normalized_alias) DO UPDATE SET team_id = excluded.team_id
                    """,
                    (team.provider, normalize_text(alias), row["id"]),
                )
            self._connection.commit()

    def resolve(self, provider: str, name: str) -> Team:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT teams.provider, teams.external_id, teams.name, teams.country,
                       teams.participant_slug, teams.country_id
                FROM team_aliases
                JOIN teams ON teams.id = team_aliases.team_id
                WHERE team_aliases.provider = ? AND team_aliases.normalized_alias = ?
                """,
                (provider, normalize_text(name)),
            ).fetchone()
        if row is None:
            raise TeamNotFoundError(f"Time não encontrado no índice: {name}")
        return Team(
            provider=row["provider"],
            external_id=row["external_id"],
            name=row["name"],
            country=row["country"],
            participant_slug=row["participant_slug"],
            country_id=row["country_id"],
        )

    def aliases(self, provider: str) -> tuple[str, ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT normalized_alias FROM team_aliases
                WHERE provider = ? ORDER BY LENGTH(normalized_alias) DESC
                """,
                (provider,),
            ).fetchall()
        return tuple(row["normalized_alias"] for row in rows)

    def resolve_mentioned(self, provider: str, text: str) -> Team:
        normalized_text = f" {normalize_text(text)} "
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT team_aliases.normalized_alias, teams.provider, teams.external_id,
                       teams.name, teams.country, teams.participant_slug, teams.country_id
                FROM team_aliases
                JOIN teams ON teams.id = team_aliases.team_id
                WHERE team_aliases.provider = ?
                ORDER BY LENGTH(team_aliases.normalized_alias) DESC
                """,
                (provider,),
            ).fetchall()
        for row in rows:
            alias = row["normalized_alias"]
            if f" {alias} " not in normalized_text:
                continue
            return Team(
                provider=row["provider"],
                external_id=row["external_id"],
                name=row["name"],
                country=row["country"],
                participant_slug=row["participant_slug"],
                country_id=row["country_id"],
            )
        raise TeamNotFoundError("Nenhum time conhecido foi identificado na pergunta.")


class QueryCache(_SqliteStore):
    def __init__(self, database_path: Path) -> None:
        super().__init__(database_path)
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS query_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            self._connection.commit()

    def get(self, cache_key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json, expires_at FROM query_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if row is None:
                return None
            if datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC):
                self._connection.execute("DELETE FROM query_cache WHERE cache_key = ?", (cache_key,))
                self._connection.commit()
                return None
            return json.loads(row["payload_json"])

    def put(self, cache_key: str, payload: dict[str, Any], ttl: timedelta) -> None:
        expires_at = (datetime.now(UTC) + ttl).isoformat()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO query_cache(cache_key, payload_json, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload_json = excluded.payload_json, expires_at = excluded.expires_at
                """,
                (cache_key, json.dumps(payload, ensure_ascii=False, sort_keys=True), expires_at),
            )
            self._connection.commit()
