import pytest

from packages.core.pipeline import JobType, JsonJobRepository, PipelineService
from services.api.store import DocumentStore
from workers.sync.main import SyncJobProcessor


pytestmark = pytest.mark.integration


def test_sync_reindexes_changed_upload(tmp_path):
    documents = DocumentStore(tmp_path)
    documents.ingest_bytes("sync.txt", b"old content")
    (documents.upload_dir / "sync.txt").write_bytes(b"new searchable content")
    jobs = JsonJobRepository(tmp_path)
    job = PipelineService(jobs).start(JobType.SYNC_DOCUMENTS, {})
    result = SyncJobProcessor(jobs, documents).process(job.job_id)
    assert result["result"]["updated"] == 1
    assert documents.search("searchable", 3)[0]["filename"] == "sync.txt"
