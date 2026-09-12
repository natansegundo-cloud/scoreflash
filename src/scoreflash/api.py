"""API HTTP local do ScoreFlash."""

from __future__ import annotations

import atexit
from contextlib import asynccontextmanager
from collections.abc import Callable
from typing import Protocol

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .catalog import seed_initial_catalog
from .config import Settings, save_api_football_key
from .errors import ScoreFlashError, TeamNotFoundError
from .services.discovery import TeamDiscoveryService
from .services.player_opportunities import PlayerOpportunityResult
from .services.questions import QueryResult, QueryService
from .storage.sqlite import QueryCache, TeamIndex


class QueryExecutor(Protocol):
    def execute(self, question: str) -> QueryResult | PlayerOpportunityResult: ...


class QueryRequest(BaseModel):
    question: str = Field(min_length=6, max_length=500)


class ApiFootballKeyRequest(BaseModel):
    api_key: str = Field(min_length=12, max_length=200)


def build_default_service(
    settings: Settings | None = None,
    discovery: TeamDiscoveryService | None = None,
) -> QueryService:
    active_settings = settings or Settings.from_environ()
    database_path = active_settings.data_dir / "scoreflash.sqlite3"
    teams = TeamIndex(database_path)
    seed_initial_catalog(teams)
    cache = QueryCache(database_path)
    return QueryService(active_settings, teams, cache, discovery)


def create_app(
    service: QueryExecutor | None = None,
    save_api_key: Callable[[str], None] = save_api_football_key,
    settings: Settings | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_environ()
    query_service = service or build_default_service(active_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            close = getattr(query_service, "close", None)
            if callable(close):
                close()

    app = FastAPI(
        title="ScoreFlash API",
        version="0.2.0",
        lifespan=lifespan,
        description="Consultas sob demanda de estatísticas de futebol.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.query_service = query_service

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/query")
    def query(request: QueryRequest) -> dict[str, object]:
        try:
            return query_service.execute(request.question).as_dict()
        except TeamNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ScoreFlashError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/settings/api-football")
    def configure_api_football(request: ApiFootballKeyRequest) -> dict[str, str]:
        if not active_settings.allow_local_key_setup:
            raise HTTPException(status_code=404, detail="Configuração local indisponível nesta versão pública.")
        configure = getattr(query_service, "configure_api_football", None)
        if not callable(configure):
            raise HTTPException(status_code=501, detail="Esta instância não aceita configuração local.")
        try:
            save_api_key(request.api_key)
            configure(request.api_key)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"status": "configured"}

    return app


app = create_app()


@atexit.register
def close_default_service() -> None:
    close = getattr(app.state.query_service, "close", None)
    if callable(close):
        close()


def run() -> None:
    uvicorn.run("scoreflash.api:app", host="127.0.0.1", port=8000, reload=True)
