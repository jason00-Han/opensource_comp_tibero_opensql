from fastapi.testclient import TestClient

from services.api import main

from packages.core.pipeline import JobType, JsonJobRepository, PipelineService
from services.api.store import DocumentStore
from workers.ingest.main import IngestJobProcessor
from workers.sync.main import SyncJobProcessor

client = TestClient(main.app)


class FakePublisher:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, str]] = []

    def publish(self, job_id: str, job_type: str) -> None:
        self.jobs.append((job_id, job_type))


class FailingPublisher:
    def publish(self, job_id: str, job_type: str) -> None:
        raise ConnectionError("broker unavailable")


def test_queued_document_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("TIBERO_DOC_DATA_DIR", str(tmp_path))
    publisher = FakePublisher()
    monkeypatch.setattr(main, "get_publisher", lambda: publisher)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["documents"] == 0

    upload = client.post(
        "/v1/documents",
        files={"file": ("guide.txt", "Tibero Doc은 문서를 청킹하고 검색합니다.", "text/plain")},
    )
    assert upload.status_code == 202
    assert upload.json()["status"] == "queued"
    assert publisher.jobs == [(upload.json()["job_id"], "index_document")]

    queued = client.get(f"/v1/jobs/{upload.json()['job_id']}")
    assert queued.json()["status"] == "queued"

    completed = IngestJobProcessor(JsonJobRepository(tmp_path), DocumentStore(tmp_path)).process(upload.json()["job_id"])
    assert completed["status"] == "completed"
    assert completed["result"]["chunks"] == 1

    status = client.get(f"/v1/jobs/{upload.json()['job_id']}")
    assert status.json()["status"] == "completed"

    search = client.post("/v1/search", json={"query": "문서 검색", "top_k": 3})
    assert search.status_code == 200
    assert search.json()["results"][0]["filename"] == "guide.txt"


def test_sync_is_queued_and_processed(tmp_path, monkeypatch):
    monkeypatch.setenv("TIBERO_DOC_DATA_DIR", str(tmp_path))
    publisher = FakePublisher()
    monkeypatch.setattr(main, "get_publisher", lambda: publisher)
    DocumentStore(tmp_path).ingest_bytes("guide.txt", b"searchable text")

    response = client.post("/v1/sync")
    assert response.status_code == 202
    assert response.json()["status"] == "queued"

    assert publisher.jobs == [(response.json()["job_id"], "sync_documents")]

    completed = SyncJobProcessor(JsonJobRepository(tmp_path), DocumentStore(tmp_path)).process(response.json()["job_id"])
    assert completed["status"] == "completed"
    assert completed["result"] == {"added": 0, "updated": 0, "deleted": 0, "skipped": 1}

def test_worker_records_extraction_failure(tmp_path):
    documents = DocumentStore(tmp_path)
    stored = documents.save_upload("empty-text.txt", b"   ")
    jobs = JsonJobRepository(tmp_path)
    job = PipelineService(jobs).start(JobType.INDEX_DOCUMENT, {"filename": stored.filename})

    result = IngestJobProcessor(jobs, documents).process(job.job_id)

    assert result["status"] == "failed"
    assert "텍스트를 추출" in result["error"]

def test_rejects_unsupported_file_before_queueing(tmp_path, monkeypatch):
    monkeypatch.setenv("TIBERO_DOC_DATA_DIR", str(tmp_path))
    publisher = FakePublisher()
    monkeypatch.setattr(main, "get_publisher", lambda: publisher)
    response = client.post(
        "/v1/documents",
        files={"file": ("image.png", b"not an image", "image/png")},
    )
    assert response.status_code == 400
    assert "지원하지 않는" in response.json()["detail"]
    assert publisher.jobs == []


def test_broker_failure_is_reported_and_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("TIBERO_DOC_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(main, "get_publisher", FailingPublisher)

    response = client.post(
        "/v1/documents",
        files={"file": ("guide.txt", b"searchable text", "text/plain")},
    )

    assert response.status_code == 503
    jobs = list(JsonJobRepository(tmp_path)._load().values())
    assert len(jobs) == 1
    assert jobs[0]["status"] == "failed"
    assert "broker unavailable" in jobs[0]["error"]


def test_missing_job_and_search_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("TIBERO_DOC_DATA_DIR", str(tmp_path))
    assert client.get("/v1/jobs/missing").status_code == 404
    response = client.post("/v1/search", json={"query": "", "top_k": 0})
    assert response.status_code == 422

