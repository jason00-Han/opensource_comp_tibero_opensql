import pytest

from packages.core.pipeline import JobStatus, JobType, JsonJobRepository, PipelineService
from tests.conftest import FakePublisher


pytestmark = pytest.mark.unit


def test_service_creates_publishes_and_completes_job(tmp_path):
    publisher = FakePublisher()
    service = PipelineService(JsonJobRepository(tmp_path), publisher)
    job = service.start(JobType.INDEX_DOCUMENT, {"filename": "guide.txt"})
    assert publisher.messages == [(job.job_id, JobType.INDEX_DOCUMENT)]
    service.running(job.job_id)
    assert service.complete(job.job_id, {"chunks": 1}).status == JobStatus.COMPLETED


def test_service_get_returns_none_for_unknown_job(tmp_path):
    assert PipelineService(JsonJobRepository(tmp_path)).get("missing") is None
