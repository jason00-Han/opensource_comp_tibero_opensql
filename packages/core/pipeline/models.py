from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class PipelineStage(StrEnum):
    INGEST = "ingest"
    EMBEDDING = "embedding"
    SYNC = "sync"


class JobType(StrEnum):
    INDEX_DOCUMENT = "index_document"
    EMBED_DOCUMENT = "embed_document"
    SYNC_DOCUMENTS = "sync_documents"

    @property
    def stage(self) -> PipelineStage:
        return {
            JobType.INDEX_DOCUMENT: PipelineStage.INGEST,
            JobType.EMBED_DOCUMENT: PipelineStage.EMBEDDING,
            JobType.SYNC_DOCUMENTS: PipelineStage.SYNC,
        }[self]


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_final(self) -> bool:
        return self in {JobStatus.COMPLETED, JobStatus.FAILED}


@dataclass(frozen=True)
class PipelineJob:
    job_id: str
    type: JobType
    stage: PipelineStage
    status: JobStatus
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> PipelineJob:
        job_type = JobType(value["type"])
        return cls(
            job_id=value["job_id"],
            type=job_type,
            stage=PipelineStage(value.get("stage", job_type.stage)),
            status=JobStatus(value["status"]),
            payload=value.get("payload", {}),
            result=value.get("result"),
            error=value.get("error"),
            created_at=value["created_at"],
            updated_at=value["updated_at"],
        )
