from __future__ import annotations

import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Protocol

from filelock import FileLock
from psycopg.types.json import Jsonb

from packages.core.database import connect, database_dsn
from packages.core.pipeline.models import JobStatus, JobType, PipelineJob
from packages.core.pipeline.publisher import JobPublisher


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JobRepository(Protocol):
    """Persistence boundary for local JSON or an OpenSQL implementation."""

    def create(self, job: PipelineJob) -> PipelineJob: ...
    def get(self, job_id: str) -> PipelineJob | None: ...
    def save(self, job: PipelineJob) -> PipelineJob: ...


class JsonJobRepository:
    """Process-safe local repository used by the standalone MVP."""

    def __init__(self, data_dir: Path | None = None) -> None:
        configured = os.getenv("TIBERO_DOC_DATA_DIR")
        self.data_dir = data_dir or (Path(configured) if configured else Path.home() / ".tibero-doc" / "data")
        self.path = self.data_dir / "jobs.json"
        self.lock_path = self.data_dir / "jobs.lock"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with FileLock(str(self.lock_path)):
            yield

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"작업 상태를 읽을 수 없습니다: {exc}") from exc

    def _save(self, jobs: dict[str, dict[str, Any]]) -> None:
        descriptor, temporary_name = tempfile.mkstemp(dir=self.data_dir, prefix="jobs-", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                json.dump(jobs, temporary, ensure_ascii=False, indent=2)
                temporary.flush()
                os.fsync(temporary.fileno())
            Path(temporary_name).replace(self.path)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    def create(self, job: PipelineJob) -> PipelineJob:
        with self._locked():
            jobs = self._load()
            if job.job_id in jobs:
                raise ValueError(f"Job already exists: {job.job_id}")
            jobs[job.job_id] = job.to_dict()
            self._save(jobs)
        return job

    def get(self, job_id: str) -> PipelineJob | None:
        with self._locked():
            value = self._load().get(job_id)
        return PipelineJob.from_dict(value) if value else None

    def save(self, job: PipelineJob) -> PipelineJob:
        with self._locked():
            jobs = self._load()
            if job.job_id not in jobs:
                raise KeyError(job.job_id)
            jobs[job.job_id] = job.to_dict()
            self._save(jobs)
        return job


class OpenSQLJobRepository:
    """Durable pipeline job repository backed by OpenSQL."""

    uses_transactional_outbox = True

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or database_dsn()
        if not self.dsn:
            raise RuntimeError("TIBERO_DOC_DSN is not configured")

    def create(self, job: PipelineJob) -> PipelineJob:
        with connect(self.dsn) as connection:
            connection.execute(
                """
                INSERT INTO tibero_doc.pipeline_jobs
                    (job_id, job_type, stage, status, payload, result, error,
                     created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job.job_id, job.type.value, job.stage.value, job.status.value,
                    Jsonb(job.payload), Jsonb(job.result) if job.result is not None else None,
                    job.error, job.created_at, job.updated_at,
                ),
            )
            if os.getenv("PIPELINE_MODE", "queue").lower() == "queue":
                connection.execute(
                    """
                    INSERT INTO tibero_doc.outbox_events
                        (event_type, aggregate_id, payload)
                    VALUES ('pipeline.job.created', %s, %s)
                    """,
                    (job.job_id, Jsonb({"job_id": job.job_id, "job_type": job.type.value})),
                )
        return job

    def get(self, job_id: str) -> PipelineJob | None:
        with connect(self.dsn) as connection:
            row = connection.execute(
                """
                SELECT job_id, job_type, stage, status, payload, result, error,
                       created_at, updated_at
                  FROM tibero_doc.pipeline_jobs
                 WHERE job_id = %s
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return PipelineJob.from_dict({
            "job_id": row[0], "type": row[1], "stage": row[2], "status": row[3],
            "payload": row[4], "result": row[5], "error": row[6],
            "created_at": row[7].isoformat(), "updated_at": row[8].isoformat(),
        })

    def save(self, job: PipelineJob) -> PipelineJob:
        with connect(self.dsn) as connection:
            cursor = connection.execute(
                """
                UPDATE tibero_doc.pipeline_jobs
                   SET status = %s, stage = %s, payload = %s, result = %s,
                       error = %s, updated_at = %s
                 WHERE job_id = %s
                """,
                (
                    job.status.value, job.stage.value, Jsonb(job.payload),
                    Jsonb(job.result) if job.result is not None else None,
                    job.error, job.updated_at, job.job_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(job.job_id)
        return job


def job_repository_from_env() -> JobRepository:
    return OpenSQLJobRepository() if database_dsn() else JsonJobRepository()


class PipelinePublishError(RuntimeError):
    pass


class PipelineStateError(RuntimeError):
    pass


class PipelineService:
    def __init__(self, repository: JobRepository, publisher: JobPublisher | None = None) -> None:
        self.repository = repository
        self.publisher = publisher

    def start(self, job_type: JobType, payload: dict[str, Any]) -> PipelineJob:
        now = _now()
        job = self.repository.create(PipelineJob(
            job_id=uuid.uuid4().hex,
            type=job_type,
            stage=job_type.stage,
            status=JobStatus.QUEUED,
            payload=payload,
            result=None,
            error=None,
            created_at=now,
            updated_at=now,
        ))
        if self.publisher is None:
            return job
        # OpenSQLJobRepository committed the job and outbox row atomically. A separate
        # publisher delivers it; direct publish here would create duplicate messages.
        if getattr(self.repository, "uses_transactional_outbox", False):
            return job
        try:
            self.publisher.publish(job.job_id, job.type)
        except Exception as exc:
            self.fail(job.job_id, f"작업을 큐에 넣지 못했습니다: {exc}")
            raise PipelinePublishError(str(exc)) from exc
        return job

    def get(self, job_id: str) -> PipelineJob | None:
        return self.repository.get(job_id)

    def running(self, job_id: str) -> PipelineJob:
        return self._transition(job_id, JobStatus.RUNNING)

    def complete(self, job_id: str, result: dict[str, Any]) -> PipelineJob:
        return self._transition(job_id, JobStatus.COMPLETED, result=result)

    def fail(self, job_id: str, error: str) -> PipelineJob:
        return self._transition(job_id, JobStatus.FAILED, error=error)

    def retry(self, job_id: str) -> PipelineJob:
        """Moves a failed job back to queued when RabbitMQ redelivers it."""
        return self._transition(job_id, JobStatus.QUEUED)

    def _transition(
        self,
        job_id: str,
        status: JobStatus,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> PipelineJob:
        current = self.repository.get(job_id)
        if current is None:
            raise KeyError(job_id)
        allowed = {
            JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.FAILED},
            JobStatus.RUNNING: {JobStatus.COMPLETED, JobStatus.FAILED},
            JobStatus.COMPLETED: set(),
            JobStatus.FAILED: {JobStatus.QUEUED},
        }
        if status not in allowed[current.status]:
            raise PipelineStateError(f"Invalid job transition: {current.status} -> {status}")
        updated = PipelineJob(
            job_id=current.job_id,
            type=current.type,
            stage=current.stage,
            status=status,
            payload=current.payload,
            result=result,
            error=error,
            created_at=current.created_at,
            updated_at=_now(),
        )
        return self.repository.save(updated)
