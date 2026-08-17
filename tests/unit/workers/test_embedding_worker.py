import pytest

from packages.core.embedding_service import EmbeddingService, JsonEmbeddingRepository
from packages.core.pipeline import JobType, JsonJobRepository, PipelineService
from services.api.store import DocumentStore
from workers.embedding.main import EmbeddingJobProcessor


pytestmark = pytest.mark.unit


class FakeProvider:
    model = "worker-test"

    def embed(self, texts):
        return [[0.1, float(len(text))] for text in texts]


def test_embedding_worker_generates_all_chunk_vectors(tmp_path):
    documents = DocumentStore(tmp_path)
    record = documents.ingest_bytes("guide.txt", b"embedding worker content")
    jobs = JsonJobRepository(tmp_path)
    job = PipelineService(jobs).start(JobType.EMBED_DOCUMENT, {"document_id": record.document_id})
    service = EmbeddingService(FakeProvider(), JsonEmbeddingRepository(tmp_path))
    result = EmbeddingJobProcessor(jobs, documents, service).process(job.job_id)
    assert result["status"] == "completed"
    assert result["result"]["embeddings"] == record.chunk_count


def test_embedding_worker_fails_when_chunks_are_missing(tmp_path):
    jobs = JsonJobRepository(tmp_path)
    job = PipelineService(jobs).start(JobType.EMBED_DOCUMENT, {"document_id": "missing"})
    service = EmbeddingService(FakeProvider(), JsonEmbeddingRepository(tmp_path))
    assert EmbeddingJobProcessor(jobs, DocumentStore(tmp_path), service).process(job.job_id)["status"] == "failed"
