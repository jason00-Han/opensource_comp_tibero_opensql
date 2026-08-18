import os
import uuid

import pytest

from packages.core.object_storage import S3ObjectStorage


pytestmark = [pytest.mark.integration, pytest.mark.minio]


def test_real_minio_round_trip(monkeypatch):
    required = ("S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        pytest.fail(f"missing MinIO settings: {', '.join(missing)}")
    monkeypatch.setenv("S3_BUCKET", os.getenv("S3_TEST_BUCKET", "tibero-documents-test"))
    storage = S3ObjectStorage()
    key = f"pytest/{uuid.uuid4().hex}.txt"
    try:
        storage.put(key, b"minio integration", "text/plain")
        assert storage.get(key) == b"minio integration"
        assert storage.download_url(key).startswith("http")
    finally:
        storage.delete(key)
