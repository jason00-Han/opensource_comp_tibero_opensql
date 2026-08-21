from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable

import pika

from packages.core.pipeline.models import JobType
from packages.core.pipeline.publisher import RabbitMQPublisher
from packages.core.pipeline.routing import queue_for
from packages.core.observability import WorkerHeartbeat, configure_loki_logging


LOGGER = logging.getLogger(__name__)


def consume_jobs(job_type: JobType, process: Callable[[str], object]) -> None:
    """Consume one worker type's durable queue; safe to run in many processes."""
    broker = RabbitMQPublisher()
    configure_loki_logging(f"worker-{job_type.stage.value}")
    heartbeat = WorkerHeartbeat(job_type.stage.value)
    heartbeat.start()
    queue_name = queue_for(job_type)
    connection = pika.BlockingConnection(pika.URLParameters(broker.url))
    channel = connection.channel()
    retry_queue = f"{queue_name}.retry"
    dead_queue = f"{queue_name}.dlq"
    retry_delay = int(os.getenv("RABBITMQ_RETRY_DELAY_MS", "5000"))
    max_retries = int(os.getenv("RABBITMQ_MAX_RETRIES", "3"))
    channel.queue_declare(queue=dead_queue, durable=True)
    channel.queue_declare(queue=retry_queue, durable=True, arguments={
        "x-message-ttl": retry_delay,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": queue_name,
    })
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_qos(prefetch_count=int(os.getenv("WORKER_PREFETCH", "1")))

    def consume(ch, method, properties, body: bytes) -> None:
        job_id = "unknown"
        started = None
        try:
            job_id = json.loads(body)["job_id"]
            started = heartbeat.processing(job_id)
            result = process(job_id)
            if isinstance(result, dict) and result.get("status") == "failed":
                raise RuntimeError(result.get("error") or "worker reported failure")
            heartbeat.finished(started, True)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as exc:
            if started is not None:
                heartbeat.finished(started, False)
            headers = dict(properties.headers or {})
            attempts = int(headers.get("x-retry-count", 0)) + 1
            destination = retry_queue if attempts <= max_retries else dead_queue
            headers.update({"x-retry-count": attempts, "x-last-error": str(exc)[:500]})
            LOGGER.exception("Job failed; routing to %s (attempt %s/%s)", destination, attempts, max_retries)
            ch.basic_publish(
                exchange="", routing_key=destination, body=body,
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent,
                    content_type="application/json",
                    message_id=properties.message_id,
                    headers=headers,
                ),
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=queue_name, on_message_callback=consume)
    LOGGER.info("Worker consuming queue %s", queue_name)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        LOGGER.info("Worker shutdown requested")
        if channel.is_open:
            channel.stop_consuming()
    finally:
        if connection.is_open:
            connection.close()
