from __future__ import annotations

import uuid

import pytest

from packages.core.database import connect
from packages.core.embedding_service import EmbeddingService, LocalHashEmbeddingProvider, OpenSQLEmbeddingRepository
from services.api.store import OpenSQLDocumentStore
from packages.core.knowledge_graph import KnowledgeGraphService


pytestmark = [pytest.mark.integration, pytest.mark.openproxy]


def test_document_version_embedding_and_hybrid_search(tmp_path):
    filename = f"platform-{uuid.uuid4().hex}.txt"
    store = OpenSQLDocumentStore(data_dir=tmp_path)
    document_ids: list[str] = []
    try:
        first = store.ingest_bytes(filename, "OpenSQL은 기업 문서를 안정적으로 관리합니다.".encode())
        document_ids.append(first.document_id)
        second = store.ingest_bytes(filename, "김민수 팀장은 OpenSQL과 TiberoDB를 티맥스연구소 프로젝트에서 자동 임베딩하고 검색합니다.".encode())
        document_ids.append(second.document_id)
        assert second.version == 2

        provider = LocalHashEmbeddingProvider(384)
        service = EmbeddingService(provider, OpenSQLEmbeddingRepository())
        result = service.embed_document(second.document_id, store.chunks_for_document(second.document_id))
        assert result["embeddings"] == second.chunk_count
        graph_result = KnowledgeGraphService().index_document(store.workspace_id, second.document_id, store.chunks_for_document(second.document_id))
        assert graph_result["entities"] >= 3
        graph = KnowledgeGraphService().document_graph(store.workspace_id, second.document_id)
        assert any(item["name"] == "OpenSQL" for item in graph["entities"])
        assert graph["relationships"]

        query = "자동 임베딩 검색"
        matches = store.search(query, 5, provider.embed([query])[0], provider.model)
        assert matches
        assert matches[0]["document_id"] == second.document_id
        assert matches[0]["vector_rank"] is not None
        graph_matches = store.search("OpenSQL", 5, provider.embed(["OpenSQL"])[0], provider.model)
        assert graph_matches[0]["graph_rank"] is not None
        assert "OpenSQL" in graph_matches[0]["entities"]
        assert [item["version"] for item in store.versions(filename)] == [2, 1]
    finally:
        current = next((item for item in store.list_documents(1000, 0) if item["filename"] == filename), None)
        if current:
            store.delete_document(current["document_id"])
        with connect() as connection:
            connection.execute("DELETE FROM tibero_doc.document_versions WHERE filename = %s", (filename,))
            connection.execute("DELETE FROM tibero_doc.outbox_events WHERE payload ->> 'filename' = %s", (filename,))
            connection.execute("DELETE FROM tibero_doc.entities e WHERE NOT EXISTS (SELECT 1 FROM tibero_doc.document_entities de WHERE de.entity_id=e.entity_id)")
