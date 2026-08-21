from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Header, HTTPException
from psycopg.types.json import Jsonb

from packages.core.database import connect, database_dsn


LOCAL_ID = "00000000-0000-0000-0000-000000000001"
ROLE_LEVEL = {"viewer": 1, "editor": 2, "manager": 3, "owner": 4}


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    workspace_id: str
    organization_id: str
    email: str
    display_name: str
    role: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(user_id: str, workspace_id: str, name: str = "cli", dsn: str | None = None, expires_minutes: int | None = None) -> str:
    raw = "tdoc_" + secrets.token_urlsafe(32)
    with connect(dsn) as connection:
        connection.execute(
            "INSERT INTO tibero_doc.api_tokens (user_id, workspace_id, token_hash, name, expires_at) VALUES (%s, %s, %s, %s, %s)",
            (user_id, workspace_id, _hash(raw), name, datetime.now(UTC) + timedelta(minutes=expires_minutes) if expires_minutes else None),
        )
    return raw


def bootstrap_owner(email: str, display_name: str, dsn: str | None = None, password: str | None = None) -> tuple[str, str]:
    """Create or reuse an owner and a private default workspace."""
    slug = hashlib.sha256(email.lower().encode()).hexdigest()[:12]
    with connect(dsn) as connection:
        user = connection.execute(
            """
            INSERT INTO tibero_doc.users (email, display_name) VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
            RETURNING user_id
            """,
            (email.lower(), display_name),
        ).fetchone()[0]
        organization = connection.execute(
            """
            INSERT INTO tibero_doc.organizations (name, slug, created_by)
            VALUES (%s, %s, %s) ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
            RETURNING organization_id
            """,
            (f"{display_name}'s Organization", f"org-{slug}", user),
        ).fetchone()[0]
        workspace = connection.execute(
            """
            INSERT INTO tibero_doc.workspaces (organization_id, name, slug, created_by)
            VALUES (%s, 'General', 'general', %s)
            ON CONFLICT (organization_id, slug) DO UPDATE SET name = EXCLUDED.name
            RETURNING workspace_id
            """,
            (organization, user),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO tibero_doc.workspace_members (workspace_id, user_id, role)
            VALUES (%s, %s, 'owner') ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = 'owner'
            """,
            (workspace, user),
        )
        if password:
            from argon2 import PasswordHasher
            connection.execute("UPDATE tibero_doc.users SET password_hash = %s WHERE user_id = %s", (PasswordHasher().hash(password), user))
    return issue_token(str(user), str(workspace), "bootstrap", dsn), str(workspace)


def login(email: str, password: str, workspace_id: str | None = None, dsn: str | None = None) -> dict:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    with connect(dsn) as connection:
        workspace_filter = "AND m.workspace_id = %s" if workspace_id else ""
        params = (email.lower(), workspace_id) if workspace_id else (email.lower(),)
        row = connection.execute(
            f"""
            SELECT u.user_id, u.password_hash, m.workspace_id
              FROM tibero_doc.users u JOIN tibero_doc.workspace_members m ON m.user_id = u.user_id
             WHERE u.email = %s AND u.status = 'active' {workspace_filter}
             ORDER BY m.joined_at LIMIT 1
            """, params,
        ).fetchone()
    if not row or not row[1]:
        raise ValueError("이메일 또는 비밀번호가 올바르지 않습니다.")
    try:
        PasswordHasher().verify(row[1], password)
    except VerifyMismatchError as exc:
        raise ValueError("이메일 또는 비밀번호가 올바르지 않습니다.") from exc
    access = issue_token(str(row[0]), str(row[2]), "login", dsn, 15)
    refresh = "tdoc_ref_" + secrets.token_urlsafe(40)
    with connect(dsn) as connection:
        connection.execute(
            "INSERT INTO tibero_doc.refresh_tokens (user_id, workspace_id, token_hash, expires_at) VALUES (%s, %s, %s, %s)",
            (row[0], row[2], _hash(refresh), datetime.now(UTC) + timedelta(days=30)),
        )
    return {"access_token": access, "refresh_token": refresh, "expires_in": 900, "workspace_id": str(row[2])}


def refresh_access_token(refresh_token: str, dsn: str | None = None) -> dict:
    with connect(dsn) as connection:
        row = connection.execute(
            """SELECT refresh_token_id, user_id, workspace_id FROM tibero_doc.refresh_tokens
               WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > now() FOR UPDATE""",
            (_hash(refresh_token),),
        ).fetchone()
        if not row:
            raise ValueError("Refresh Token이 유효하지 않습니다.")
        connection.execute("UPDATE tibero_doc.refresh_tokens SET revoked_at = now() WHERE refresh_token_id = %s", (row[0],))
    access = issue_token(str(row[1]), str(row[2]), "refresh", dsn, 15)
    new_refresh = "tdoc_ref_" + secrets.token_urlsafe(40)
    with connect(dsn) as connection:
        connection.execute("INSERT INTO tibero_doc.refresh_tokens (user_id, workspace_id, token_hash, expires_at) VALUES (%s, %s, %s, %s)", (row[1], row[2], _hash(new_refresh), datetime.now(UTC) + timedelta(days=30)))
    return {"access_token": access, "refresh_token": new_refresh, "expires_in": 900, "workspace_id": str(row[2])}


def can_access_document(context: AuthContext, document_id: str, permission: str = "read") -> bool:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT d.visibility, d.owner_user_id,
                   EXISTS (SELECT 1 FROM tibero_doc.document_acl a WHERE a.document_id = d.document_id
                     AND ((a.principal_type='user' AND a.principal_id=%s)
                       OR (a.principal_type='group' AND a.principal_id IN
                           (SELECT group_id FROM tibero_doc.group_members WHERE user_id=%s))))
              FROM tibero_doc.documents d WHERE d.document_id=%s AND d.workspace_id=%s
            """, (context.user_id, context.user_id, document_id, context.workspace_id),
        ).fetchone()
    return bool(row and (row[0] == "workspace" or str(row[1]) == context.user_id or row[2] or context.role in {"manager", "owner"}))


def authenticate(authorization: str | None = Header(default=None)) -> AuthContext:
    if os.getenv("AUTH_MODE", "required") == "disabled" or not database_dsn():
        return AuthContext(LOCAL_ID, LOCAL_ID, LOCAL_ID, "local@tibero-doc.invalid", "Local Owner", "owner")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    token_hash = _hash(authorization[7:])
    with connect() as connection:
        row = connection.execute(
            """
            SELECT u.user_id, t.workspace_id, w.organization_id, u.email, u.display_name, m.role, t.token_id
              FROM tibero_doc.api_tokens t
              JOIN tibero_doc.users u ON u.user_id = t.user_id AND u.status = 'active'
              JOIN tibero_doc.workspaces w ON w.workspace_id = t.workspace_id
              JOIN tibero_doc.workspace_members m ON m.workspace_id = t.workspace_id AND m.user_id = t.user_id
             WHERE t.token_hash = %s AND t.revoked_at IS NULL
               AND (t.expires_at IS NULL OR t.expires_at > now())
            """,
            (token_hash,),
        ).fetchone()
        if row:
            connection.execute("UPDATE tibero_doc.api_tokens SET last_used_at = now() WHERE token_id = %s", (row[6],))
    if not row:
        raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 토큰입니다.")
    return AuthContext(*(str(value) for value in row[:3]), row[3], row[4], row[5])


def require_role(context: AuthContext, minimum: str) -> None:
    if ROLE_LEVEL[context.role] < ROLE_LEVEL[minimum]:
        raise HTTPException(status_code=403, detail=f"{minimum} 이상의 권한이 필요합니다.")


def create_invitation(context: AuthContext, email: str | None, role: str, dsn: str | None = None) -> str:
    require_role(context, "manager")
    raw = "tdoc_inv_" + secrets.token_urlsafe(24)
    with connect(dsn) as connection:
        connection.execute(
            """
            INSERT INTO tibero_doc.invitations (workspace_id, email, role, token_hash, invited_by, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (context.workspace_id, email.lower() if email else None, role, _hash(raw), context.user_id, datetime.now(UTC) + timedelta(days=7)),
        )
    return raw


def accept_invitation(invite_token: str, email: str, display_name: str, dsn: str | None = None) -> tuple[str, str]:
    with connect(dsn) as connection:
        invitation = connection.execute(
            """
            SELECT invitation_id, workspace_id, email, role FROM tibero_doc.invitations
             WHERE token_hash = %s AND accepted_at IS NULL AND expires_at > now() FOR UPDATE
            """,
            (_hash(invite_token),),
        ).fetchone()
        if not invitation or (invitation[2] and invitation[2].lower() != email.lower()):
            raise ValueError("초대 링크가 유효하지 않거나 만료되었습니다.")
        user = connection.execute(
            """
            INSERT INTO tibero_doc.users (email, display_name) VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name RETURNING user_id
            """,
            (email.lower(), display_name),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO tibero_doc.workspace_members (workspace_id, user_id, role) VALUES (%s, %s, %s)
            ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = EXCLUDED.role
            """,
            (invitation[1], user, invitation[3]),
        )
        connection.execute("UPDATE tibero_doc.invitations SET accepted_at = now() WHERE invitation_id = %s", (invitation[0],))
    return issue_token(str(user), str(invitation[1]), "invite", dsn), str(invitation[1])


def audit(context: AuthContext, action: str, resource_type: str, resource_id: str | None = None, details: dict | None = None) -> None:
    if not database_dsn() or os.getenv("AUTH_MODE") == "disabled":
        return
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO tibero_doc.audit_logs
                (organization_id, workspace_id, actor_user_id, action, resource_type, resource_id, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (context.organization_id, context.workspace_id, context.user_id, action, resource_type, resource_id, Jsonb(details or {})),
        )
