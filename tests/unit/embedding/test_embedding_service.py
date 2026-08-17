import json

import pytest

from packages.core.embedding_service import EmbeddingService, JsonEmbeddingRepository


pytestmark = pytest.mark.unit


class FakeProvider:
    model = "service-test"

    def embed(self, texts):
        return [[float(index)] for index, _ in enumerate(texts)]


def test_embedding_service_preserves_chunk_indexes(tmp_path):
    repository = JsonEmbeddingRepository(tmp_path)
    result = EmbeddingService(FakeProvider(), repository).embed_document("doc", [
        {"chunk_index": 2, "content": "two"},
        {"chunk_index": 5, "content": "five"},
    ])
    assert result["embeddings"] == 2
    stored = json.loads((tmp_path / "embeddings.json").read_text())
    assert [item["chunk_index"] for item in stored] == [2, 5]


def test_embedding_service_replaces_existing_document_vectors(tmp_path):
    repository = JsonEmbeddingRepository(tmp_path)
    service = EmbeddingService(FakeProvider(), repository)
    service.embed_document("doc", [{"chunk_index": 0, "content": "old"}])
    service.embed_document("doc", [{"chunk_index": 1, "content": "new"}])
    assert [item["chunk_index"] for item in json.loads((tmp_path / "embeddings.json").read_text())] == [1]
