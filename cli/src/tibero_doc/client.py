from pathlib import Path

import httpx

from tibero_doc.config import get_api_url


class TiberoDocClient:

    def __init__(self, api_url: str | None = None):
        self.api_url = (
            api_url or get_api_url()
        ).rstrip("/")

        self.client = httpx.Client(
            base_url=self.api_url,
            timeout=30.0,
        )

    def health(self):
        response = self.client.get(
            "/health"
        )

        response.raise_for_status()

        return response.json()

    def search(
        self,
        query: str,
        top_k: int = 5,
    ):
        response = self.client.post(
            "/v1/search",
            json={
                "query": query,
                "top_k": top_k,
            },
        )

        response.raise_for_status()

        return response.json()

    def ingest(self, file_path: Path):

        with file_path.open("rb") as f:

            response = self.client.post(
                "/v1/documents",
                files={
                    "file": (
                        file_path.name,
                        f,
                    )
                },
            )

        response.raise_for_status()

        return response.json()

    def sync(self):
        response = self.client.post(
            "/v1/sync"
        )

        response.raise_for_status()

        return response.json()