from __future__ import annotations

import logging
import os

from packages.core.pipeline import JobPublisher, JobType, JsonJobRepository, PipelineService, RabbitMQPublisher
from services.api.store import DocumentStore
from workers.common import consume_jobs


LOGGER = logging.getLogger(__name__)


class IngestJobProcessor:
    def __init__(
        self,
        jobs: JsonJobRepository | None = None,
        documents: DocumentStore | None = None,
        publisher: JobPublisher | None = None,
    ) -> None:
        repository = jobs or JsonJobRepository()
        self.pipeline = PipelineService(repository)
        self.next_stage = PipelineService(repository, publisher) if publisher else None
        self.documents = documents or DocumentStore()

    def process(self, job_id: str) -> dict:
        job = self.pipeline.get(job_id)
        if job is None:
            raise KeyError(f"Unknown job: {job_id}")
        if job.status.is_final:
            return job.to_dict()
        if job.type != JobType.INDEX_DOCUMENT:
            raise ValueError(f"Ingest worker cannot process: {job.type}")

        self.pipeline.running(job_id)
        try:
            record = self.documents.index_upload(job.payload["filename"])
            result = {
                "document_id": record.document_id,
                "filename": record.filename,
                "size": record.size,
                "chunks": record.chunk_count,
            }
            if self.next_stage:
                embedding_job = self.next_stage.start(JobType.EMBED_DOCUMENT, {
                    "document_id": record.document_id,
                    "source_job_id": job_id,
                })
                result["embedding_job_id"] = embedding_job.job_id
        except Exception as exc:
            LOGGER.exception("Ingest job %s failed", job_id)
            return self.pipeline.fail(job_id, str(exc)).to_dict()
        return self.pipeline.complete(job_id, result).to_dict()


def run_worker() -> None:
    consume_jobs(JobType.INDEX_DOCUMENT, IngestJobProcessor(publisher=RabbitMQPublisher()).process)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_worker()
