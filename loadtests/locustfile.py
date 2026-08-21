from __future__ import annotations

import os
import random

from locust import HttpUser, between, task


class DocumentUser(HttpUser):
    wait_time = between(0.2, 1.0)

    def on_start(self):
        self.headers = {"Authorization": f"Bearer {os.environ['TIBERO_DOC_LOAD_TOKEN']}"}
        self.queries = os.getenv("LOAD_QUERIES", "장애 복구,보안 정책,데이터베이스 운영").split(",")

    @task(8)
    def search(self):
        with self.client.post("/v1/search", json={"query": random.choice(self.queries), "top_k": 5},
                              headers=self.headers, name="POST /v1/search", catch_response=True) as response:
            if response.elapsed.total_seconds() > 2:
                response.failure("search latency exceeded 2 seconds")

    @task(2)
    def health(self):
        self.client.get("/health", name="GET /health")
