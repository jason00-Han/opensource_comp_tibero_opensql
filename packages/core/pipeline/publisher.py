from __future__ import annotations

import json
import os
from typing import Protocol

import pika

from packages.core.pipeline.models import JobType
from packages.core.pipeline.routing import queue_for


class JobPublisher(Protocol):
    def publish(self, job_id: str, job_type: JobType) -> None: ...


class RabbitMQPublisher:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")

    def publish(self, job_id: str, job_type: JobType) -> None:
        queue_name = queue_for(job_type)
        connection = pika.BlockingConnection(pika.URLParameters(self.url))
        try:
            channel = connection.channel()
            channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_publish(
                exchange="",
                routing_key=queue_name,
                body=json.dumps({"job_id": job_id}).encode(),
                properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent),
            )
        finally:
            connection.close()
