from pathlib import Path

import httpx

from tibero_doc.config import get_api_url, load_access_token


class TiberoDocClient:

    def __init__(self, api_url: str | None = None):
        self.api_url = (
            api_url or get_api_url()
        ).rstrip("/")

        token = load_access_token(self.api_url)
        self.client = httpx.Client(
            base_url=self.api_url,
            timeout=30.0,
            headers={"Authorization": f"Bearer {token}"} if token else {},
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

    def documents(self, limit: int = 100, offset: int = 0):
        response = self.client.get("/v1/documents", params={"limit": limit, "offset": offset})
        response.raise_for_status()
        return response.json()

    def document(self, document_id: str):
        response = self.client.get(f"/v1/documents/{document_id}")
        response.raise_for_status()
        return response.json()

    def delete_document(self, document_id: str):
        response = self.client.delete(f"/v1/documents/{document_id}")
        response.raise_for_status()

    def versions(self, document_id: str):
        response = self.client.get(f"/v1/documents/{document_id}/versions")
        response.raise_for_status()
        return response.json()

    def job(self, job_id: str):
        response = self.client.get(f"/v1/jobs/{job_id}")
        response.raise_for_status()
        return response.json()

    def me(self):
        response = self.client.get("/v1/me")
        response.raise_for_status()
        return response.json()

    def invite(self, email: str | None, role: str):
        response = self.client.post("/v1/invitations", json={"email": email, "role": role})
        response.raise_for_status()
        return response.json()

    def join(self, invite_token: str, email: str, display_name: str):
        response = self.client.post("/v1/auth/join", json={"invite_token": invite_token, "email": email, "display_name": display_name})
        response.raise_for_status()
        return response.json()

    def login(self, email: str, password: str):
        response = self.client.post("/v1/auth/login", json={"email": email, "password": password})
        response.raise_for_status()
        return response.json()

    def refresh(self, refresh_token: str):
        response = self.client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
        response.raise_for_status()
        return response.json()

    def audit_logs(self, limit: int = 100):
        response = self.client.get("/v1/admin/audit-logs", params={"limit": limit})
        response.raise_for_status()
        return response.json()
