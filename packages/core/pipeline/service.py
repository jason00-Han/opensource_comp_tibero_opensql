from __future__ import annotations

import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Protocol

import fcntl

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
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

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
            JobStatus.FAILED: set(),
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
