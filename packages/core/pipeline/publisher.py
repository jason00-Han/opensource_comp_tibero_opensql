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
            retry_queue = f"{queue_name}.retry"
            dead_queue = f"{queue_name}.dlq"
            channel.queue_declare(queue=dead_queue, durable=True)
            channel.queue_declare(
                queue=retry_queue,
                durable=True,
                arguments={
                    "x-message-ttl": int(os.getenv("RABBITMQ_RETRY_DELAY_MS", "5000")),
                    "x-dead-letter-exchange": "",
                    "x-dead-letter-routing-key": queue_name,
                },
            )
            channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_publish(
                exchange="",
                routing_key=queue_name,
                body=json.dumps({"job_id": job_id}).encode(),
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent,
                    content_type="application/json",
                    message_id=job_id,
                    headers={"x-retry-count": 0},
                ),
            )
        finally:
            connection.close()
