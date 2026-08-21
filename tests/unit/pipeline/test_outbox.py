from packages.core.pipeline.models import JobType
from packages.core.pipeline.outbox import OutboxEvent, OutboxPublisher


class Repository:
    def __init__(self, events):
        self.events = events
        self.published_ids = []
        self.failures = []

    def claim_batch(self, _limit): return self.events
    def published(self, event_id): self.published_ids.append(event_id)
    def failed(self, event_id, error): self.failures.append((event_id, error))


class Publisher:
    def __init__(self): self.messages = []
    def publish(self, job_id, job_type): self.messages.append((job_id, job_type))


def test_outbox_routes_pipeline_job_and_marks_published():
    repository = Repository([OutboxEvent("event-1", "pipeline.job.created", "job-1",
        {"job_id": "job-1", "job_type": "index_document"}, 0)])
    publisher = Publisher()
    assert OutboxPublisher(repository, publisher).publish_once() == (1, 0)
    assert publisher.messages == [("job-1", JobType.INDEX_DOCUMENT)]
    assert repository.published_ids == ["event-1"]
