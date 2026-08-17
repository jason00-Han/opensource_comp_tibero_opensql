from __future__ import annotations

import logging
import os

from packages.core.embedding_service import EmbeddingService, JsonEmbeddingRepository, OpenAICompatibleEmbeddingProvider
from packages.core.pipeline import JobType, JsonJobRepository, PipelineService
from services.api.store import DocumentStore
from workers.common import consume_jobs


LOGGER = logging.getLogger(__name__)


class EmbeddingJobProcessor:
    def __init__(
        self,
        jobs: JsonJobRepository | None = None,
        documents: DocumentStore | None = None,
        embeddings: EmbeddingService | None = None,
    ) -> None:
        self.pipeline = PipelineService(jobs or JsonJobRepository())
        self.documents = documents or DocumentStore()
        self.embeddings = embeddings or EmbeddingService(
            OpenAICompatibleEmbeddingProvider(),
            JsonEmbeddingRepository(),
        )

    def process(self, job_id: str) -> dict:
        job = self.pipeline.get(job_id)
        if job is None:
            raise KeyError(f"Unknown job: {job_id}")
        if job.status.is_final:
            return job.to_dict()
        if job.type != JobType.EMBED_DOCUMENT:
            raise ValueError(f"Embedding worker cannot process: {job.type}")

        self.pipeline.running(job_id)
        try:
            document_id = job.payload["document_id"]
            chunks = self.documents.chunks_for_document(document_id)
            if not chunks:
                raise ValueError(f"No chunks found for document: {document_id}")
            result = self.embeddings.embed_document(document_id, chunks)
        except Exception as exc:
            LOGGER.exception("Embedding job %s failed", job_id)
            return self.pipeline.fail(job_id, str(exc)).to_dict()
        return self.pipeline.complete(job_id, result).to_dict()


def run_worker() -> None:
    consume_jobs(JobType.EMBED_DOCUMENT, EmbeddingJobProcessor().process)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_worker()
