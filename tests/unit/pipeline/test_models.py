import pytest

from packages.core.pipeline import JobStatus, JobType, PipelineJob, PipelineStage


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "job_type,stage",
    [
        (JobType.INDEX_DOCUMENT, PipelineStage.INGEST),
        (JobType.EMBED_DOCUMENT, PipelineStage.EMBEDDING),
        (JobType.SYNC_DOCUMENTS, PipelineStage.SYNC),
    ],
)
def test_job_type_maps_to_stage(job_type, stage):
    assert job_type.stage == stage


def test_pipeline_job_round_trip():
    value = {
        "job_id": "job-1", "type": "index_document", "stage": "ingest", "status": "queued",
        "payload": {"filename": "a.txt"}, "result": None, "error": None,
        "created_at": "now", "updated_at": "now",
    }
    assert PipelineJob.from_dict(value).to_dict() == value
    assert JobStatus.COMPLETED.is_final
    assert not JobStatus.RUNNING.is_final
