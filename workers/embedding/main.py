from __future__ import annotations

import logging
import os
from packages.core.lineage import record_lineage

from packages.core.embedding_service import EmbeddingService, embedding_provider_from_env, embedding_repository_from_env
from packages.core.pipeline import JobType, PipelineService, job_repository_from_env
from packages.core.pipeline.service import JobRepository
from services.api.store import DocumentStore, document_store_from_env
from workers.common import consume_jobs


LOGGER = logging.getLogger(__name__)


class EmbeddingJobProcessor:
    def __init__(
        self,
        jobs: JobRepository | None = None,
        documents: DocumentStore | None = None,
        embeddings: EmbeddingService | None = None,
    ) -> None:
        self.pipeline = PipelineService(jobs or job_repository_from_env())
        self.documents = documents
        self.embeddings = embeddings or EmbeddingService(
            embedding_provider_from_env(),
            embedding_repository_from_env(),
        )

    def process(self, job_id: str) -> dict:
        job = self.pipeline.get(job_id)
        if job is None:
            raise KeyError(f"Unknown job: {job_id}")
        if job.status.value == "completed":
            return job.to_dict()
        if job.status.value == "failed":
            job = self.pipeline.retry(job_id)
        if job.type != JobType.EMBED_DOCUMENT:
            raise ValueError(f"Embedding worker cannot process: {job.type}")

        self.pipeline.running(job_id)
        try:
            document_id = job.payload["document_id"]
            documents = self.documents or document_store_from_env(job.payload.get("workspace_id"), job.payload.get("user_id"))
            chunks = documents.chunks_for_document(document_id)
            if not chunks:
                raise ValueError(f"No chunks found for document: {document_id}")
            result = self.embeddings.embed_document(document_id, chunks)
            record_lineage("document.embedded", workspace_id=job.payload.get("workspace_id"),
                           document_id=document_id, output_model=result.get("model"),
                           job_id=job_id, metadata={"embeddings": result.get("embeddings")})
        except Exception as exc:
            LOGGER.exception("Embedding job %s failed", job_id)
            return self.pipeline.fail(job_id, str(exc)).to_dict()
        return self.pipeline.complete(job_id, result).to_dict()


def run_worker() -> None:
    consume_jobs(JobType.EMBED_DOCUMENT, EmbeddingJobProcessor().process)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_worker()
