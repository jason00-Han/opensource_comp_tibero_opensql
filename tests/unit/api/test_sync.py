import pytest


pytestmark = pytest.mark.unit


def test_sync_creates_queued_job(api_client, fake_publisher):
    response = api_client.post("/v1/sync")
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert fake_publisher.messages == [(response.json()["job_id"], "sync_documents")]
