import pytest

from packages.core.pipeline import JobType, JsonJobRepository, PipelineService
from services.api.store import DocumentStore
from workers.sync.main import SyncJobProcessor


pytestmark = pytest.mark.unit


def test_sync_reports_unchanged_file(tmp_path):
    documents = DocumentStore(tmp_path)
    documents.ingest_bytes("guide.txt", b"unchanged")
    jobs = JsonJobRepository(tmp_path)
    job = PipelineService(jobs).start(JobType.SYNC_DOCUMENTS, {})
    result = SyncJobProcessor(jobs, documents).process(job.job_id)
    assert result["result"] == {"added": 0, "updated": 0, "deleted": 0, "skipped": 1}


def test_sync_removes_deleted_upload(tmp_path):
    documents = DocumentStore(tmp_path)
    documents.ingest_bytes("guide.txt", b"delete me")
    (documents.upload_dir / "guide.txt").unlink()
    jobs = JsonJobRepository(tmp_path)
    job = PipelineService(jobs).start(JobType.SYNC_DOCUMENTS, {})
    result = SyncJobProcessor(jobs, documents).process(job.job_id)
    assert result["result"]["deleted"] == 1
    assert documents.stats()["documents"] == 0
