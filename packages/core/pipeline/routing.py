from __future__ import annotations

import os

from packages.core.pipeline.models import JobType


DEFAULT_QUEUES = {
    JobType.INDEX_DOCUMENT: "tibero-doc.ingest",
    JobType.EMBED_DOCUMENT: "tibero-doc.embedding",
    JobType.SYNC_DOCUMENTS: "tibero-doc.sync",
}

QUEUE_ENV_VARS = {
    JobType.INDEX_DOCUMENT: "RABBITMQ_INGEST_QUEUE",
    JobType.EMBED_DOCUMENT: "RABBITMQ_EMBEDDING_QUEUE",
    JobType.SYNC_DOCUMENTS: "RABBITMQ_SYNC_QUEUE",
}


def queue_for(job_type: JobType | str) -> str:
    resolved = JobType(job_type)
    return os.getenv(QUEUE_ENV_VARS[resolved], DEFAULT_QUEUES[resolved])
