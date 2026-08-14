import pytest

from packages.core.pipeline import (
    JobStatus,
    JobType,
    JsonJobRepository,
    PipelineService,
    PipelineStage,
    PipelineStateError,
)
from packages.core.pipeline.routing import queue_for


class FakePublisher:
    def __init__(self) -> None:
        self.messages = []

    def publish(self, job_id, job_type) -> None:
        self.messages.append((job_id, job_type))


def test_pipeline_creates_routes_and_completes_job(tmp_path, monkeypatch):
    monkeypatch.setenv("RABBITMQ_INGEST_QUEUE", "test.ingest")
    repository = JsonJobRepository(tmp_path)
    publisher = FakePublisher()
    pipeline = PipelineService(repository, publisher)

    job = pipeline.start(JobType.INDEX_DOCUMENT, {"filename": "guide.txt"})

    assert job.stage == PipelineStage.INGEST
    assert job.status == JobStatus.QUEUED
    assert queue_for(job.type) == "test.ingest"
    assert publisher.messages == [(job.job_id, JobType.INDEX_DOCUMENT)]

    pipeline.running(job.job_id)
    completed = pipeline.complete(job.job_id, {"chunks": 2})
    assert completed.status == JobStatus.COMPLETED
    assert completed.result == {"chunks": 2}


def test_pipeline_rejects_transition_from_final_state(tmp_path):
    pipeline = PipelineService(JsonJobRepository(tmp_path))
    job = pipeline.start(JobType.SYNC_DOCUMENTS, {})
    pipeline.running(job.job_id)
    pipeline.complete(job.job_id, {"updated": 0})

    with pytest.raises(PipelineStateError):
        pipeline.running(job.job_id)