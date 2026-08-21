from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.api.rate_limit import RateLimitMiddleware
import uuid


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/limited")
    def limited():
        return {"ok": True}

    client = TestClient(app)
    headers = {"Authorization": f"Bearer test-{uuid.uuid4().hex}"}
    assert client.get("/limited", headers=headers).status_code == 200
    assert client.get("/limited", headers=headers).status_code == 200
    response = client.get("/limited", headers=headers)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
