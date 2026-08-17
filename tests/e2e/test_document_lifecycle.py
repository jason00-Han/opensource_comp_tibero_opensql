import json
import os
import uuid

import pika
import pytest
from fastapi.testclient import TestClient

from packages.core.embedding_service import EmbeddingService, JsonEmbeddingRepository
from packages.core.pipeline import JsonJobRepository, RabbitMQPublisher
from packages.core.pipeline.models import JobType
from services.api import main
from services.api.store import DocumentStore
from workers.embedding.main import EmbeddingJobProcessor
from workers.ingest.main import IngestJobProcessor


pytestmark = [pytest.mark.e2e, pytest.mark.rabbitmq]


class FakeEmbeddingProvider:
    model = "e2e-model"

    def embed(self, texts):
        return [[0.1, float(len(text))] for text in texts]


def _get_job(channel, queue_name):
    method, _, body = channel.basic_get(queue_name, auto_ack=False)
    assert method is not None
    return method, json.loads(body)["job_id"]


def test_upload_ingest_embedding_status_and_search(tmp_path, monkeypatch):
    suffix = uuid.uuid4().hex
    ingest_queue = f"tibero-doc.e2e.ingest.{suffix}"
    embedding_queue = f"tibero-doc.e2e.embedding.{suffix}"
    monkeypatch.setenv("TIBERO_DOC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RABBITMQ_INGEST_QUEUE", ingest_queue)
    monkeypatch.setenv("RABBITMQ_EMBEDDING_QUEUE", embedding_queue)
    url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/%2F")
    publisher = RabbitMQPublisher(url)
    monkeypatch.setattr(main, "get_publisher", lambda: publisher)

    connection = pika.BlockingConnection(pika.URLParameters(url))
    channel = connection.channel()
    try:
        client = TestClient(main.app)
        upload = client.post(
            "/v1/documents",
            files={"file": ("e2e.txt", b"complete RabbitMQ pipeline search", "text/plain")},
        )
        assert upload.status_code == 202

        method, ingest_job_id = _get_job(channel, ingest_queue)
        jobs = JsonJobRepository(tmp_path)
        documents = DocumentStore(tmp_path)
        ingested = IngestJobProcessor(jobs, documents, publisher).process(ingest_job_id)
        channel.basic_ack(method.delivery_tag)
        assert ingested["status"] == "completed"

        method, embedding_job_id = _get_job(channel, embedding_queue)
        embedding_service = EmbeddingService(FakeEmbeddingProvider(), JsonEmbeddingRepository(tmp_path))
        embedded = EmbeddingJobProcessor(jobs, documents, embedding_service).process(embedding_job_id)
        channel.basic_ack(method.delivery_tag)
        assert embedded["status"] == "completed"

        assert client.get(f"/v1/jobs/{ingest_job_id}").json()["status"] == "completed"
        results = client.post("/v1/search", json={"query": "pipeline search", "top_k": 3}).json()["results"]
        assert results[0]["filename"] == "e2e.txt"
        assert json.loads((tmp_path / "embeddings.json").read_text())[0]["model"] == "e2e-model"
    finally:
        channel.queue_delete(ingest_queue)
        channel.queue_delete(embedding_queue)
        connection.close()
