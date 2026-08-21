import pytest

from packages.core.pipeline import JobStatus, JobType, JsonJobRepository, PipelineService, PipelineStateError


pytestmark = pytest.mark.unit


@pytest.mark.parametrize("finalizer", ["complete", "fail"])
def test_final_job_cannot_return_to_running(tmp_path, finalizer):
    service = PipelineService(JsonJobRepository(tmp_path))
    job = service.start(JobType.SYNC_DOCUMENTS, {})
    service.running(job.job_id)
    if finalizer == "complete":
        service.complete(job.job_id, {})
    else:
        service.fail(job.job_id, "failure")
    with pytest.raises(PipelineStateError):
        service.running(job.job_id)


def test_queued_job_cannot_complete_without_running(tmp_path):
    service = PipelineService(JsonJobRepository(tmp_path))
    job = service.start(JobType.SYNC_DOCUMENTS, {})
    with pytest.raises(PipelineStateError):
        service.complete(job.job_id, {})


def test_failed_job_can_be_requeued_for_broker_retry(tmp_path):
    service = PipelineService(JsonJobRepository(tmp_path))
    job = service.start(JobType.INDEX_DOCUMENT, {})
    service.fail(job.job_id, "temporary outage")
    retried = service.retry(job.job_id)
    assert retried.status == JobStatus.QUEUED
