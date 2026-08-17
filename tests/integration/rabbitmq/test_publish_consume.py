import json
import os
import uuid

import pika
import pytest

from packages.core.pipeline import JobType, RabbitMQPublisher
from packages.core.pipeline.routing import queue_for


pytestmark = [pytest.mark.integration, pytest.mark.rabbitmq]


def test_durable_persistent_message_can_be_consumed(monkeypatch):
    queue_name = f"tibero-doc.test.{uuid.uuid4().hex}"
    monkeypatch.setenv("RABBITMQ_INGEST_QUEUE", queue_name)
    url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/%2F")
    RabbitMQPublisher(url).publish("job-123", JobType.INDEX_DOCUMENT)

    connection = pika.BlockingConnection(pika.URLParameters(url))
    try:
        channel = connection.channel()
        method, properties, body = channel.basic_get(queue_for(JobType.INDEX_DOCUMENT), auto_ack=False)
        assert method is not None
        assert properties.delivery_mode == pika.DeliveryMode.Persistent.value
        assert json.loads(body) == {"job_id": "job-123"}
        channel.basic_ack(method.delivery_tag)
    finally:
        if connection.is_open:
            connection.channel().queue_delete(queue_name)
        connection.close()
