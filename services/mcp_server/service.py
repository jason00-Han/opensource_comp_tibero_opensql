from __future__ import annotations

from packages.core.embedding_service import embedding_provider_from_env
from packages.core.pipeline import PipelineService, job_repository_from_env
from packages.core.pipeline.service import JobRepository
from services.api.store import DocumentStore, document_store_from_env
from services.api.auth import AuthContext, can_access_document
from packages.core.knowledge_graph import KnowledgeGraphService


class MCPDocumentService:
    def __init__(
        self,
        documents: DocumentStore | None = None,
        jobs: JobRepository | None = None,
        context: AuthContext | None = None,
    ) -> None:
        self.context = context
        self.documents = documents or document_store_from_env(
            context.workspace_id if context else None,
            context.user_id if context else None,
        )
        self.pipeline = PipelineService(jobs or job_repository_from_env())

    def search(self, query: str, top_k: int = 5) -> dict:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= top_k <= 100:
            raise ValueError("top_k must be between 1 and 100")
        provider = embedding_provider_from_env()
        vector = provider.embed([query])[0]
        return {
            "query": query,
            "mode": "hybrid",
            "results": self.documents.search(query, top_k, vector, provider.model),
        }

    def list_documents(self, limit: int = 100, offset: int = 0) -> dict:
        return {"documents": self.documents.list_documents(limit, offset)}

    def get_document(self, document_id: str) -> dict:
        if self.context and not can_access_document(self.context, document_id):
            raise ValueError(f"Document not found: {document_id}")
        document = self.documents.get_document(document_id)
        if document is None:
            raise ValueError(f"Document not found: {document_id}")
        return {**document, "chunks": self.documents.chunks_for_document(document_id)}

    def job_status(self, job_id: str) -> dict:
        job = self.pipeline.get(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        return job.to_dict()

    def stats(self) -> dict:
        return self.documents.stats()

    def graph(self, document_id: str) -> dict:
        if self.context and not can_access_document(self.context, document_id):
            raise ValueError(f"Document not found: {document_id}")
        document = self.documents.get_document(document_id)
        if document is None:
            raise ValueError(f"Document not found: {document_id}")
        workspace_id = self.context.workspace_id if self.context else "00000000-0000-0000-0000-000000000001"
        return {"document_id": document_id, **KnowledgeGraphService().document_graph(workspace_id, document_id)}
