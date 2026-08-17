import httpx
import pytest

from packages.core.embedding_service import OpenAICompatibleEmbeddingProvider


pytestmark = pytest.mark.unit


def test_provider_orders_vectors_by_response_index():
    def handler(request):
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]},
        ]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleEmbeddingProvider("http://test/v1", "model", client=client)
        assert provider.embed(["a", "b"]) == [[1.0], [2.0]]


def test_provider_rejects_vector_count_mismatch():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))) as client:
        provider = OpenAICompatibleEmbeddingProvider("http://test/v1", "model", client=client)
        with pytest.raises(RuntimeError):
            provider.embed(["a"])
