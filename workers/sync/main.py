from __future__ import annotations

import logging
import os

from packages.core.pipeline import JobPublisher, JobType, PipelineService, RabbitMQPublisher, job_repository_from_env
from packages.core.pipeline.service import JobRepository
from services.api.store import DocumentStore, document_store_from_env
from workers.common import consume_jobs
from packages.core.knowledge_graph import KnowledgeGraphService


LOGGER = logging.getLogger(__name__)


class SyncJobProcessor:
    def __init__(self, jobs: JobRepository | None = None, documents: DocumentStore | None = None, publisher: JobPublisher | None = None) -> None:
        repository = jobs or job_repository_from_env()
        self.pipeline = PipelineService(repository)
        self.next_stage = PipelineService(repository, publisher) if publisher else None
        self.documents = documents

    def process(self, job_id: str) -> dict:
        job = self.pipeline.get(job_id)
        if job is None:
            raise KeyError(f"Unknown job: {job_id}")
        if job.status.value == "completed":
            return job.to_dict()
        if job.status.value == "failed":
            job = self.pipeline.retry(job_id)
        if job.type != JobType.SYNC_DOCUMENTS:
            raise ValueError(f"Sync worker cannot process: {job.type}")

        self.pipeline.running(job_id)
        try:
            documents = self.documents or document_store_from_env(job.payload.get("workspace_id"), job.payload.get("user_id"))
            result = documents.sync()
            if result.get("document_ids"):
                result["graphs"] = [
                    KnowledgeGraphService().index_document(
                        job.payload.get("workspace_id") or "00000000-0000-0000-0000-000000000001",
                        document_id,
                        documents.chunks_for_document(document_id),
                    )
                    for document_id in result["document_ids"]
                ]
            if self.next_stage:
                result["embedding_job_ids"] = [
                    self.next_stage.start(JobType.EMBED_DOCUMENT, {"document_id": document_id, "source_job_id": job_id, "workspace_id": job.payload.get("workspace_id"), "user_id": job.payload.get("user_id")}).job_id
                    for document_id in result.get("document_ids", [])
                ]
        except Exception as exc:
            LOGGER.exception("Sync job %s failed", job_id)
            return self.pipeline.fail(job_id, str(exc)).to_dict()
        return self.pipeline.complete(job_id, result).to_dict()


def run_worker() -> None:
    consume_jobs(JobType.SYNC_DOCUMENTS, SyncJobProcessor(publisher=RabbitMQPublisher()).process)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_worker()
