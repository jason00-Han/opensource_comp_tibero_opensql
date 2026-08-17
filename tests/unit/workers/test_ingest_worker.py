import pytest

from packages.core.pipeline import JobType, JsonJobRepository, PipelineService
from services.api.store import DocumentStore
from tests.conftest import FakePublisher
from workers.ingest.main import IngestJobProcessor


pytestmark = pytest.mark.unit


def test_ingest_extracts_chunks_and_enqueues_embedding(tmp_path):
    documents = DocumentStore(tmp_path)
    stored = documents.save_upload("guide.txt", b"ingest worker document")
    jobs = JsonJobRepository(tmp_path)
    publisher = FakePublisher()
    job = PipelineService(jobs).start(JobType.INDEX_DOCUMENT, {"filename": stored.filename})
    result = IngestJobProcessor(jobs, documents, publisher).process(job.job_id)
    assert result["status"] == "completed"
    assert result["result"]["chunks"] == 1
    assert publisher.messages[0][1] == JobType.EMBED_DOCUMENT


def test_ingest_records_extraction_failure(tmp_path):
    documents = DocumentStore(tmp_path)
    stored = documents.save_upload("blank.txt", b"   ")
    jobs = JsonJobRepository(tmp_path)
    job = PipelineService(jobs).start(JobType.INDEX_DOCUMENT, {"filename": stored.filename})
    result = IngestJobProcessor(jobs, documents).process(job.job_id)
    assert result["status"] == "failed"
    assert "텍스트를 추출" in result["error"]
