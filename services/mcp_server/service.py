from __future__ import annotations

from packages.core.pipeline import JsonJobRepository, PipelineService
from services.api.store import DocumentStore


class MCPDocumentService:
    def __init__(
        self,
        documents: DocumentStore | None = None,
        jobs: JsonJobRepository | None = None,
    ) -> None:
        self.documents = documents or DocumentStore()
        self.pipeline = PipelineService(jobs or JsonJobRepository())

    def search(self, query: str, top_k: int = 5) -> dict:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= top_k <= 100:
            raise ValueError("top_k must be between 1 and 100")
        return {"query": query, "results": self.documents.search(query, top_k)}

    def job_status(self, job_id: str) -> dict:
        job = self.pipeline.get(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        return job.to_dict()

    def stats(self) -> dict:
        return self.documents.stats()
