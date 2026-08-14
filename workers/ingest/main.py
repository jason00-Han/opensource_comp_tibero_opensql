
import logging
import os

from packages.core.pipeline import JobType, JsonJobRepository, PipelineService
from services.api.store import DocumentStore
from workers.common import LOGGER, consume_jobs

class IngestJobProcessor:
    def __init__(self, jobs: JsonJobRepository | None = None, documents: DocumentStore | None = None) -> None:
        self.pipeline = PipelineService(jobs or JsonJobRepository())
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
            }
        except Exception as exc:
            LOGGER.exception("Ingest job %s failed", job_id)
            return self.pipeline.fail(job_id, str(exc)).to_dict()
        return self.pipeline.complete(job_id, result).to_dict()

def run_worker() -> None:
    consume_jobs(JobType.INDEX_DOCUMENT, IngestJobProcessor().process)

if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_worker()    