import json
import os
import uuid

import pika
import pytest


pytestmark = [pytest.mark.integration, pytest.mark.rabbitmq]


def test_unacked_message_is_redelivered():
    url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/%2F")
    queue = f"tibero-doc.redelivery.{uuid.uuid4().hex}"
    connection = pika.BlockingConnection(pika.URLParameters(url))
    try:
        channel = connection.channel()
        channel.queue_declare(queue=queue, durable=True)
        channel.basic_publish("", queue, json.dumps({"job_id": "retry"}),
                              properties=pika.BasicProperties(delivery_mode=2))
        first, _, _ = channel.basic_get(queue, auto_ack=False)
        assert first is not None
        channel.basic_nack(first.delivery_tag, requeue=True)
        second, _, body = channel.basic_get(queue, auto_ack=False)
        assert second is not None
        assert second.redelivered
        assert json.loads(body)["job_id"] == "retry"
        channel.basic_ack(second.delivery_tag)
        channel.queue_delete(queue)
    finally:
        connection.close()
