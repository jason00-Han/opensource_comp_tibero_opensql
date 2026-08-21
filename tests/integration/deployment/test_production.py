import os

import httpx
import pytest


pytestmark = [pytest.mark.integration, pytest.mark.production]


def _urls(name):
    value = os.getenv(name, "")
    if not value:
        pytest.fail(f"{name} is required")
    return [part.strip().rstrip("/") for part in value.split(",") if part.strip()]


def test_each_api_instance_is_ready():
    urls = _urls("PRODUCTION_API_URLS")
    assert len(urls) >= 2, "at least two API instance URLs are required"
    for url in urls:
        response = httpx.get(f"{url}/health/ready", timeout=10)
        assert response.status_code == 200, (url, response.text)


def test_nginx_tls_endpoint_and_security_headers():
    url = _urls("PRODUCTION_TLS_URL")[0]
    assert url.startswith("https://")
    response = httpx.get(f"{url}/health/live", timeout=10)
    assert response.status_code == 200
    assert response.http_version in {"HTTP/1.1", "HTTP/2"}
