from concurrent.futures import ThreadPoolExecutor

import pytest

from packages.core.pipeline import JobType, JsonJobRepository, PipelineService
from services.api.store import DocumentStore
from workers.ingest.main import IngestJobProcessor


pytestmark = pytest.mark.e2e


def test_parallel_ingest_processors_do_not_lose_index_updates(tmp_path):
    documents = DocumentStore(tmp_path)
    jobs = JsonJobRepository(tmp_path)
    job_ids = []
    for index in range(8):
        stored = documents.save_upload(f"doc-{index}.txt", f"parallel content {index}".encode())
        job_ids.append(PipelineService(jobs).start(JobType.INDEX_DOCUMENT, {"filename": stored.filename}).job_id)

    def process(job_id):
        return IngestJobProcessor(jobs, DocumentStore(tmp_path)).process(job_id)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(process, job_ids))

    assert all(result["status"] == "completed" for result in results)
    assert documents.stats() == {"documents": 8, "chunks": 8}
