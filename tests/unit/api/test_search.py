import pytest

from services.api.store import DocumentStore


pytestmark = pytest.mark.unit


def test_keyword_search_returns_ranked_chunk(api_client, tmp_path):
    DocumentStore(tmp_path).ingest_bytes("guide.txt", b"pipeline search pipeline")
    response = api_client.post("/v1/search", json={"query": "pipeline search", "top_k": 3})
    assert response.status_code == 200
    assert response.json()["results"][0]["filename"] == "guide.txt"


def test_search_request_validation(api_client):
    assert api_client.post("/v1/search", json={"query": "", "top_k": 0}).status_code == 422
