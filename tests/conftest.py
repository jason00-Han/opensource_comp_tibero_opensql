from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from services.api import main


class FakePublisher:
    def __init__(self) -> None:
        self.messages = []

    def publish(self, job_id, job_type) -> None:
        self.messages.append((job_id, job_type))


class FailingPublisher:
    def publish(self, job_id, job_type) -> None:
        raise ConnectionError("broker unavailable")


@pytest.fixture(autouse=True)
def disable_auth_for_legacy_tests(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "disabled")


@pytest.fixture
def fake_publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def api_client(tmp_path, monkeypatch, fake_publisher):
    monkeypatch.setenv("TIBERO_DOC_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(main, "get_publisher", lambda: fake_publisher)
    with TestClient(main.app) as client:
        yield client


@pytest.fixture
def openproxy_connection():
    psycopg = pytest.importorskip("psycopg")
    connection = psycopg.connect(os.environ["OPENPROXY_TEST_DSN"])
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def pytest_collection_modifyitems(config, items):
    rabbit_enabled = os.getenv("RUN_RABBITMQ_TESTS") == "1"
    openproxy_enabled = bool(os.getenv("OPENPROXY_TEST_DSN"))
    mcp_http_enabled = os.getenv("RUN_MCP_HTTP_TESTS") == "1"
    minio_enabled = os.getenv("RUN_MINIO_TESTS") == "1"
    production_enabled = os.getenv("RUN_PRODUCTION_TESTS") == "1"
    failover_enabled = os.getenv("RUN_FAILOVER_TESTS") == "1"
    for item in items:
        if "rabbitmq" in item.keywords and not rabbit_enabled:
            item.add_marker(pytest.mark.skip(reason="set RUN_RABBITMQ_TESTS=1 to run RabbitMQ tests"))
        if "openproxy" in item.keywords and not openproxy_enabled:
            item.add_marker(pytest.mark.skip(reason="set OPENPROXY_TEST_DSN to run OpenProxy tests"))
        if "mcp_http" in item.keywords and not mcp_http_enabled:
            item.add_marker(pytest.mark.skip(reason="set RUN_MCP_HTTP_TESTS=1 to run Streamable HTTP tests"))
        if "minio" in item.keywords and not minio_enabled:
            item.add_marker(pytest.mark.skip(reason="set RUN_MINIO_TESTS=1 to run MinIO tests"))
        if "production" in item.keywords and not production_enabled:
            item.add_marker(pytest.mark.skip(reason="set RUN_PRODUCTION_TESTS=1 to run deployment tests"))
        if "failover" in item.keywords and not failover_enabled:
            item.add_marker(pytest.mark.skip(reason="set RUN_FAILOVER_TESTS=1 to run the destructive failover test"))
