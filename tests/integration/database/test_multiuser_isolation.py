from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from packages.core.database import connect
from services.api.auth import bootstrap_owner
from services.api.main import app
from services.api.store import OpenSQLDocumentStore


pytestmark = [pytest.mark.integration, pytest.mark.openproxy]


def test_workspace_isolation_invitation_and_roles(monkeypatch):
    suffix = uuid.uuid4().hex
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("PIPELINE_MODE", "inline")
    owner1_email = f"owner1-{suffix}@example.com"
    owner1_token, workspace1 = bootstrap_owner(owner1_email, "Owner One", password="Strong-Test-Password!42")
    owner2_token, workspace2 = bootstrap_owner(f"owner2-{suffix}@example.com", "Owner Two")
    headers1 = {"Authorization": f"Bearer {owner1_token}"}
    headers2 = {"Authorization": f"Bearer {owner2_token}"}
    client = TestClient(app)
    document_id = None
    try:
        assert client.get("/v1/me").status_code == 401
        upload = client.post(
            "/v1/documents", headers=headers1,
            files={"file": ("shared-name.txt", b"workspace one confidential document")},
        )
        assert upload.status_code == 202
        document_id = upload.json()["document_id"]
        assert client.get("/v1/documents", headers=headers1).json()["documents"]
        assert client.get("/v1/documents", headers=headers2).json()["documents"] == []

        logged_in = client.post("/v1/auth/login", json={"email": owner1_email, "password": "Strong-Test-Password!42"})
        assert logged_in.status_code == 200
        refreshed = client.post("/v1/auth/refresh", json={"refresh_token": logged_in.json()["refresh_token"]})
        assert refreshed.status_code == 200
        replayed = client.post("/v1/auth/refresh", json={"refresh_token": logged_in.json()["refresh_token"]})
        assert replayed.status_code == 401

        invitation = client.post(
            "/v1/invitations", headers=headers1,
            json={"email": f"viewer-{suffix}@example.com", "role": "viewer"},
        )
        assert invitation.status_code == 200
        joined = client.post("/v1/auth/join", json={
            "invite_token": invitation.json()["invite_token"],
            "email": f"viewer-{suffix}@example.com", "display_name": "Viewer",
        })
        viewer_headers = {"Authorization": f"Bearer {joined.json()['access_token']}"}
        viewer_id = client.get("/v1/me", headers=viewer_headers).json()["user_id"]
        group = client.post("/v1/groups", headers=headers1, json={"name": "Readers"})
        assert group.status_code == 200
        assert client.post(f"/v1/groups/{group.json()['group_id']}/members", headers=headers1, json={"user_id": viewer_id}).status_code == 200
        assert client.post(f"/v1/documents/{document_id}/acl", headers=headers1, json={"principal_type": "group", "principal_id": group.json()["group_id"], "permission": "read"}).status_code == 200
        assert client.get("/v1/documents", headers=viewer_headers).json()["documents"]
        denied = client.post(
            "/v1/documents", headers=viewer_headers,
            files={"file": ("denied.txt", b"not allowed")},
        )
        assert denied.status_code == 403
        assert client.post("/v1/groups", headers=viewer_headers, json={"name": "Forbidden"}).status_code == 403
        assert client.get("/v1/admin/audit-logs", headers=viewer_headers).status_code == 403
        audit_response = client.get("/v1/admin/audit-logs", headers=headers1)
        assert audit_response.status_code == 200
        actions = {entry["action"] for entry in audit_response.json()["logs"]}
        assert {"member.invite", "group.create", "document.acl.grant"} <= actions
    finally:
        if document_id:
            OpenSQLDocumentStore(workspace_id=workspace1).delete_document(document_id)
        with connect() as connection:
            connection.execute("DELETE FROM tibero_doc.document_versions WHERE workspace_id IN (%s, %s)", (workspace1, workspace2))
            connection.execute("DELETE FROM tibero_doc.audit_logs WHERE workspace_id IN (%s, %s)", (workspace1, workspace2))
            connection.execute("DELETE FROM tibero_doc.organizations WHERE slug IN (%s, %s)", (f"org-{__import__('hashlib').sha256(f'owner1-{suffix}@example.com'.encode()).hexdigest()[:12]}", f"org-{__import__('hashlib').sha256(f'owner2-{suffix}@example.com'.encode()).hexdigest()[:12]}"))
            connection.execute("DELETE FROM tibero_doc.users WHERE email LIKE %s", (f"%-{suffix}@example.com",))
