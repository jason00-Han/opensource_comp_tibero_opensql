import pytest


pytestmark = pytest.mark.unit


def test_created_job_can_be_read(api_client):
    upload = api_client.post("/v1/documents", files={"file": ("guide.txt", b"job status")})
    response = api_client.get(f"/v1/jobs/{upload.json()['job_id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_missing_job_returns_404(api_client):
    assert api_client.get("/v1/jobs/missing").status_code == 404
