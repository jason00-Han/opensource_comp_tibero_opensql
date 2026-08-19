from pathlib import Path

import httpx
import click

from tibero_doc.config import get_api_url, load_access_token


class TiberoDocClient:

    _NEW_API_PREFIXES = (
        "/v1/agent/", "/v1/groups", "/v1/workspaces", "/v1/users",
        "/v1/admin/storage-status", "/v1/admin/retention-plan",
    )

    @classmethod
    def _compatibility_hint(cls, response: httpx.Response) -> None:
        if response.status_code == 404 and response.request.url.path.startswith(cls._NEW_API_PREFIXES):
            raise click.ClickException(
                "CLI는 최신 버전이지만 API 서버가 이전 코드로 실행 중입니다. "
                "API 터미널에서 Ctrl+C 후 `tibero-doc serve`를 다시 실행하세요."
            )

    def __init__(self, api_url: str | None = None):
        self.api_url = (
            api_url or get_api_url()
        ).rstrip("/")

        token = load_access_token(self.api_url)
        self.client = httpx.Client(
            base_url=self.api_url,
            timeout=30.0,
            headers={"Authorization": f"Bearer {token}"} if token else {},
            event_hooks={"response": [self._compatibility_hint]},
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
        mode: str = "hybrid",
    ):
        response = self.client.post(
            "/v1/search",
            json={
                "query": query,
                "top_k": top_k,
                "mode": mode,
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

    def document_graph(self, document_id: str):
        response = self.client.get(f"/v1/documents/{document_id}/graph")
        response.raise_for_status()
        return response.json()

    def reindex_graph(self):
        response = self.client.post("/v1/graph/reindex")
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

    def stats(self):
        response = self.client.get("/v1/stats")
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

    def ask(self, question: str, top_k: int = 5):
        response = self.client.post("/v1/agent/ask", json={"question": question, "top_k": top_k})
        response.raise_for_status()
        return response.json()

    def groups(self):
        response = self.client.get("/v1/groups"); response.raise_for_status(); return response.json()

    def create_group(self, name: str):
        response = self.client.post("/v1/groups", json={"name": name}); response.raise_for_status(); return response.json()

    def add_group_member(self, group_id: str, user_id: str):
        response = self.client.post(f"/v1/groups/{group_id}/members", json={"user_id": user_id}); response.raise_for_status(); return response.json()

    def remove_group_member(self, group_id: str, user_id: str):
        response = self.client.delete(f"/v1/groups/{group_id}/members/{user_id}"); response.raise_for_status()

    def acl(self, document_id: str):
        response = self.client.get(f"/v1/documents/{document_id}/acl"); response.raise_for_status(); return response.json()

    def grant_acl(self, document_id: str, principal_type: str, principal_id: str, permission: str):
        response = self.client.post(f"/v1/documents/{document_id}/acl", json={"principal_type": principal_type, "principal_id": principal_id, "permission": permission}); response.raise_for_status(); return response.json()

    def revoke_acl(self, document_id: str, principal_type: str, principal_id: str):
        response = self.client.delete(f"/v1/documents/{document_id}/acl/{principal_type}/{principal_id}"); response.raise_for_status()

    def workspaces(self):
        response = self.client.get("/v1/workspaces"); response.raise_for_status(); return response.json()

    def switch_workspace(self, workspace_id: str):
        response = self.client.post(f"/v1/workspaces/{workspace_id}/switch"); response.raise_for_status(); return response.json()

    def users(self):
        response = self.client.get("/v1/users"); response.raise_for_status(); return response.json()

    def change_role(self, user_id: str, role: str):
        response = self.client.patch(f"/v1/users/{user_id}/role", json={"role": role}); response.raise_for_status(); return response.json()

    def disable_user(self, user_id: str):
        response = self.client.post(f"/v1/users/{user_id}/disable"); response.raise_for_status(); return response.json()

    def storage_status(self):
        response = self.client.get("/v1/admin/storage-status"); response.raise_for_status(); return response.json()

    def retention_plan(self, hot_days: int, cold_days: int, delete_days: int):
        response = self.client.get("/v1/admin/retention-plan", params={"hot_days": hot_days, "cold_days": cold_days, "delete_days": delete_days})
        response.raise_for_status(); return response.json()

    def download(self, document_id: str) -> httpx.Response:
        response = self.client.get(f"/v1/documents/{document_id}/download", follow_redirects=True)
        response.raise_for_status()
        return response
