import pytest

from packages.core.pipeline import JobType, JsonJobRepository, PipelineService
from services.api.store import DocumentStore
from workers.ingest.main import IngestJobProcessor


pytestmark = pytest.mark.e2e


def test_blank_document_reaches_failed_terminal_state(tmp_path):
    documents = DocumentStore(tmp_path)
    stored = documents.save_upload("blank.txt", b"   ")
    jobs = JsonJobRepository(tmp_path)
    job = PipelineService(jobs).start(JobType.INDEX_DOCUMENT, {"filename": stored.filename})
    result = IngestJobProcessor(jobs, documents).process(job.job_id)
    assert result["status"] == "failed"
    assert PipelineService(jobs).get(job.job_id).status.is_final
