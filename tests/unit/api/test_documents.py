import pytest

from packages.core.pipeline import JsonJobRepository
from services.api import main
from tests.conftest import FailingPublisher


pytestmark = pytest.mark.unit


def test_upload_is_persisted_and_queued(api_client, fake_publisher):
    response = api_client.post(
        "/v1/documents",
        files={"file": ("guide.txt", b"searchable document", "text/plain")},
    )
    body = response.json()
    assert response.status_code == 202
    assert body["status"] == "queued"
    assert fake_publisher.messages == [(body["job_id"], "index_document")]


@pytest.mark.parametrize("filename,content", [("image.png", b"png"), ("empty.txt", b"")])
def test_upload_validation(api_client, fake_publisher, filename, content):
    response = api_client.post("/v1/documents", files={"file": (filename, content)})
    assert response.status_code == 400
    assert fake_publisher.messages == []


def test_broker_failure_returns_503_and_records_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("TIBERO_DOC_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(main, "get_publisher", FailingPublisher)
    from fastapi.testclient import TestClient

    response = TestClient(main.app).post(
        "/v1/documents", files={"file": ("guide.txt", b"searchable", "text/plain")}
    )
    assert response.status_code == 503
    jobs = list(JsonJobRepository(tmp_path)._load().values())
    assert jobs[0]["status"] == "failed"
