from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

from psycopg.rows import dict_row

from packages.core.database import connect, database_dsn
from packages.core.pipeline.models import JobType
from packages.core.pipeline.publisher import JobPublisher, RabbitMQPublisher

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutboxEvent:
    event_id: str
    event_type: str
    aggregate_id: str
    payload: dict
    attempts: int


class OpenSQLOutboxRepository:
    """Claims rows with SKIP LOCKED so multiple publishers can run safely."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or database_dsn()
        if not self.dsn:
            raise RuntimeError("TIBERO_DOC_DSN is not configured")

    def claim_batch(self, limit: int = 100) -> list[OutboxEvent]:
        try:
            with connect(self.dsn) as connection:
                with connection.cursor(row_factory=dict_row) as cursor:
                    rows = cursor.execute("""
                UPDATE tibero_doc.outbox_events o
                   SET locked_at = now(), locked_by = %s
                 WHERE event_id IN (
                       SELECT event_id FROM tibero_doc.outbox_events
                        WHERE published_at IS NULL
                          AND (locked_at IS NULL OR locked_at < now() - interval '5 minutes')
                        ORDER BY created_at
                        FOR UPDATE SKIP LOCKED LIMIT %s)
                RETURNING event_id::text, event_type, aggregate_id, payload, attempts
                """,
                    (os.getenv("HOSTNAME", "outbox-publisher"), limit)).fetchall()
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "42703":
                raise RuntimeError(
                    "Outbox 스키마가 오래되었습니다. `tibero-doc migrate` 실행 후 Worker를 다시 시작하세요."
                ) from exc
            raise
        return [OutboxEvent(**row) for row in rows]

    def published(self, event_id: str) -> None:
        with connect(self.dsn) as connection:
            connection.execute(
                "UPDATE tibero_doc.outbox_events SET published_at=now(), locked_at=NULL, last_error=NULL WHERE event_id=%s",
                (event_id,),
            )

    def failed(self, event_id: str, error: str) -> None:
        with connect(self.dsn) as connection:
            connection.execute(
                "UPDATE tibero_doc.outbox_events SET attempts=attempts+1, locked_at=NULL, last_error=%s WHERE event_id=%s",
                (error[:1000], event_id),
            )


class OutboxPublisher:
    EVENT_ROUTES: dict[str, JobType] = {}

    def __init__(self, repository: OpenSQLOutboxRepository | None = None, publisher: JobPublisher | None = None) -> None:
        self.repository = repository or OpenSQLOutboxRepository()
        self.publisher = publisher or RabbitMQPublisher()

    def publish_once(self, limit: int = 100) -> tuple[int, int]:
        published = failed = 0
        for event in self.repository.claim_batch(limit):
            route = (JobType(event.payload["job_type"])
                     if event.event_type == "pipeline.job.created"
                     else self.EVENT_ROUTES.get(event.event_type))
            if route is None:
                if event.event_type.startswith("document."):
                    # Change-capture events are retained as lineage; pipeline jobs are
                    # emitted separately in the same transaction and routed to workers.
                    self.repository.published(event.event_id)
                    published += 1
                    continue
                self.repository.failed(event.event_id, f"unsupported event: {event.event_type}")
                failed += 1
                continue
            try:
                job_id = event.payload.get("job_id", event.aggregate_id)
                self.publisher.publish(job_id, route)
                self.repository.published(event.event_id)
                published += 1
            except Exception as exc:
                LOGGER.exception("Outbox event %s publication failed", event.event_id)
                self.repository.failed(event.event_id, str(exc))
                failed += 1
        return published, failed

    def run_forever(self) -> None:
        interval = float(os.getenv("OUTBOX_POLL_SECONDS", "1"))
        while True:
            self.publish_once(int(os.getenv("OUTBOX_BATCH_SIZE", "100")))
            time.sleep(interval)
