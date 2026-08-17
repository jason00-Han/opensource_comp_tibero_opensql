import pytest

from packages.core.pipeline import JobType
from packages.core.pipeline.routing import queue_for


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "job_type,expected",
    [
        (JobType.INDEX_DOCUMENT, "tibero-doc.ingest"),
        (JobType.EMBED_DOCUMENT, "tibero-doc.embedding"),
        (JobType.SYNC_DOCUMENTS, "tibero-doc.sync"),
    ],
)
def test_default_queue_routes(job_type, expected):
    assert queue_for(job_type) == expected


def test_queue_can_be_overridden(monkeypatch):
    monkeypatch.setenv("RABBITMQ_INGEST_QUEUE", "custom.ingest")
    assert queue_for(JobType.INDEX_DOCUMENT) == "custom.ingest"
