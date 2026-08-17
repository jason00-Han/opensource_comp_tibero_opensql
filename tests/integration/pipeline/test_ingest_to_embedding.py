import pytest

from packages.core.embedding_service import EmbeddingService, JsonEmbeddingRepository
from packages.core.pipeline import JobType, JsonJobRepository, PipelineService
from services.api.store import DocumentStore
from tests.conftest import FakePublisher
from workers.embedding.main import EmbeddingJobProcessor
from workers.ingest.main import IngestJobProcessor


pytestmark = pytest.mark.integration


class FakeProvider:
    model = "pipeline-test"

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def test_ingest_result_drives_embedding_stage(tmp_path):
    documents = DocumentStore(tmp_path)
    stored = documents.save_upload("pipeline.txt", b"pipeline integration")
    jobs = JsonJobRepository(tmp_path)
    publisher = FakePublisher()
    ingest_job = PipelineService(jobs).start(JobType.INDEX_DOCUMENT, {"filename": stored.filename})
    ingest = IngestJobProcessor(jobs, documents, publisher).process(ingest_job.job_id)
    embedding_job_id = ingest["result"]["embedding_job_id"]
    embedding = EmbeddingJobProcessor(
        jobs,
        documents,
        EmbeddingService(FakeProvider(), JsonEmbeddingRepository(tmp_path)),
    ).process(embedding_job_id)
    assert embedding["status"] == "completed"
    assert embedding["result"]["embeddings"] == 1
