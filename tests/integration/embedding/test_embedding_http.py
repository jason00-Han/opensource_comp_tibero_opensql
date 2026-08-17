import json

import httpx
import pytest

from packages.core.embedding_service import OpenAICompatibleEmbeddingProvider


pytestmark = pytest.mark.integration


def test_openai_compatible_provider_http_contract():
    captured = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "data": [
                {"index": 0, "embedding": [3.0, 0.0]},
                {"index": 1, "embedding": [5.0, 1.0]},
            ]
        })

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAICompatibleEmbeddingProvider(
            base_url="http://embedding.test/v1",
            model="contract-model",
            api_key="secret",
            client=client,
        )
        assert provider.embed(["one", "three"]) == [[3.0, 0.0], [5.0, 1.0]]

    assert captured == {
        "url": "http://embedding.test/v1/embeddings",
        "authorization": "Bearer secret",
        "body": {"model": "contract-model", "input": ["one", "three"]},
    }
