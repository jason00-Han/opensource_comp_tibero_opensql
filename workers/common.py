from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable

import pika

from packages.core.pipeline.models import JobType
from packages.core.pipeline.publisher import RabbitMQPublisher
from packages.core.pipeline.routing import queue_for


LOGGER = logging.getLogger(__name__)


def consume_jobs(job_type: JobType, process: Callable[[str], object]) -> None:
    """Consume one worker type's durable queue; safe to run in many processes."""
    broker = RabbitMQPublisher()
    queue_name = queue_for(job_type)
    connection = pika.BlockingConnection(pika.URLParameters(broker.url))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_qos(prefetch_count=int(os.getenv("WORKER_PREFETCH", "1")))

    def consume(ch, method, _properties, body: bytes) -> None:
        try:
            process(json.loads(body)["job_id"])
        except Exception:
            LOGGER.exception("Invalid or unknown %s job message", job_type)
        finally:
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
