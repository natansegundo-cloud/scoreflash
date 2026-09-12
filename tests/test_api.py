from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from scoreflash.api import build_default_service, create_app
from scoreflash.config import Settings
from scoreflash.errors import TeamNotFoundError
from scoreflash.services.questions import QueryResult


class FakeQueryService:
    def execute(self, question: str) -> QueryResult:
        return QueryResult(
            answer=f"Resposta para: {question}",
            team="Newell's Old Boys",
            metric="finalizações",
            games=5,
            venue="any",
            average=10.4,
            unit="count",
            matches=(),
        )


class ConfigurableFakeQueryService(FakeQueryService):
    def __init__(self) -> None:
        self.configured_key = ""

    def configure_api_football(self, api_key: str) -> None:
        self.configured_key = api_key


class MissingTeamDiscovery:
    def resolve(self, question: str, hinted_name: str = "") -> None:
        raise TeamNotFoundError("Time não encontrado")


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app(FakeQueryService()))
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)

    def test_health_reports_ok(self) -> None:
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_query_returns_a_serialized_result(self) -> None:
        response = self.client.post(
            "/api/query",
            json={"question": "Qual a média de finalizações do Newell's?"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["team"], "Newell's Old Boys")
        self.assertEqual(payload["average"], 10.4)

    def test_configures_api_football_key_without_returning_it(self) -> None:
        service = ConfigurableFakeQueryService()
        with TestClient(create_app(service, save_api_key=lambda _: None)) as client:
            response = client.post(
                "/api/settings/api-football",
                json={"api_key": "local-test-key-123"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "configured"})
        self.assertEqual(service.configured_key, "local-test-key-123")

    def test_public_instance_does_not_offer_local_key_configuration(self) -> None:
        service = ConfigurableFakeQueryService()
        settings = Settings(
            flashscore_signature="",
            data_dir=Path("data"),
            allow_local_key_setup=False,
        )
        with TestClient(create_app(service, save_api_key=lambda _: None, settings=settings)) as client:
            response = client.post(
                "/api/settings/api-football",
                json={"api_key": "local-test-key-123"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(service.configured_key, "")

    def test_real_service_can_read_sqlite_from_an_api_request_thread(self) -> None:
        with TemporaryDirectory() as directory:
            service = build_default_service(
                Settings(flashscore_signature="", data_dir=Path(directory)),
                MissingTeamDiscovery(),  # type: ignore[arg-type]
            )
            with TestClient(create_app(service)) as client:
                response = client.post(
                    "/api/query",
                    json={"question": "Qual a media de finalizacoes do Time Inexistente?"},
                )

        self.assertEqual(response.status_code, 404)
