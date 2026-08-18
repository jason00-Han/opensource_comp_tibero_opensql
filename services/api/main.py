from __future__ import annotations

import os
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from packages.core.database import check_database, database_dsn
from packages.core.embedding_service import (
    EmbeddingService,
    embedding_provider_from_env,
    embedding_repository_from_env,
)
from packages.core.pipeline import (
    JobPublisher,
    JobType,
    PipelinePublishError,
    PipelineService,
    RabbitMQPublisher,
    job_repository_from_env,
)
from services.api.store import DocumentStore, document_store_from_env
from services.api.auth import AuthContext, accept_invitation, audit, authenticate, can_access_document, create_invitation, login, refresh_access_token, require_role
from services.api.email_service import send_invitation
from services.api.rate_limit import RateLimitMiddleware
from packages.core.database import connect
from psycopg.rows import dict_row


app = FastAPI(
    title="Tibero Doc API",
    version="1.0.0",
    description="OpenSQL 기반 자동화 AI 문서 관리 및 하이브리드 검색 API",
)
app.add_middleware(RateLimitMiddleware)
web_dir = Path(__file__).resolve().parents[1] / "web"
if web_dir.exists():
    app.mount("/ui", StaticFiles(directory=web_dir, html=True), name="web-ui")


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    mode: str = Field(default="hybrid", pattern="^(keyword|vector|hybrid)$")


class InvitationRequest(BaseModel):
    email: str | None = None
    role: str = Field(default="viewer", pattern="^(viewer|editor|manager)$")


class JoinRequest(BaseModel):
    invite_token: str
    email: str
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: str
    password: str
    workspace_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class GroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class GroupMemberRequest(BaseModel):
    user_id: str


class ACLRequest(BaseModel):
    principal_type: str = Field(pattern="^(user|group)$")
    principal_id: str
    permission: str = Field(default="read", pattern="^(read|write|manage)$")


def get_store() -> DocumentStore:
    return document_store_from_env()


def _store_for(context: AuthContext) -> DocumentStore:
    return document_store_from_env(context.workspace_id, context.user_id) if database_dsn() else get_store()


def get_job_repository():
    return job_repository_from_env()


def get_publisher() -> JobPublisher:
    return RabbitMQPublisher()


def get_pipeline() -> PipelineService:
    publisher = None if os.getenv("PIPELINE_MODE", "queue") == "inline" else get_publisher()
    return PipelineService(get_job_repository(), publisher)


def get_embeddings() -> EmbeddingService:
    return EmbeddingService(embedding_provider_from_env(), embedding_repository_from_env())


def _embed_document(document_id: str, store: DocumentStore) -> dict:
    chunks = store.chunks_for_document(document_id)
    if not chunks:
        raise ValueError(f"No chunks found for document: {document_id}")
    return get_embeddings().embed_document(document_id, chunks)


@app.get("/")
def root() -> dict:
    return {"name": "Tibero Doc API", "status": "running", "docs": "/docs"}


@app.get("/health")
def health() -> dict:
    try:
        stats = get_store().stats()
        database = check_database() if database_dsn() else {"database": "local-json", "is_replica": False}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "status": "healthy",
        "components": {
            "api": "healthy",
            "storage": "healthy",
            "opensql": "healthy" if database_dsn() else "not-configured",
            "search": "healthy",
        },
        "database": database,
        **stats,
    }


@app.get("/health/live")
def liveness() -> dict:
    return {"status": "alive"}


@app.get("/health/ready")
def readiness() -> dict:
    return health()


@app.post("/v1/documents", status_code=202)
async def ingest_document(file: UploadFile = File(...), context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "editor")
    store = _store_for(context)
    try:
        stored = store.save_upload(file.filename or "document", await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pipeline = get_pipeline()
    try:
        job = pipeline.start(JobType.INDEX_DOCUMENT, {"filename": stored.filename, "document_id": stored.document_id, "object_key": stored.object_key, "workspace_id": context.workspace_id, "user_id": context.user_id})
        if os.getenv("PIPELINE_MODE", "queue") == "inline":
            pipeline.running(job.job_id)
            record = store.index_upload(stored.filename, stored.object_key) if hasattr(store, "objects") else store.index_upload(stored.filename)
            embedding = _embed_document(record.document_id, store)
            job = pipeline.complete(job.job_id, {
                "document_id": record.document_id, "filename": record.filename,
                "version": record.version, "chunks": record.chunk_count,
                **embedding,
            })
    except PipelinePublishError as exc:
        raise HTTPException(status_code=503, detail="RabbitMQ 연결에 실패했습니다.") from exc
    except Exception as exc:
        current = pipeline.get(job.job_id) if "job" in locals() else None
        if current and not current.status.is_final:
            pipeline.fail(job.job_id, str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(context, "document.upload", "document", stored.document_id, {"filename": stored.filename})
    return {
        "job_id": job.job_id, "document_id": (job.result or {}).get("document_id", stored.document_id),
        "filename": stored.filename, "size": stored.size, "status": job.status,
        "result": job.result,
    }


@app.get("/v1/documents")
def list_documents(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), context: AuthContext = Depends(authenticate)) -> dict:
    return {"documents": _store_for(context).list_documents(limit, offset), "limit": limit, "offset": offset}


@app.get("/v1/documents/{document_id}")
def get_document(document_id: str, context: AuthContext = Depends(authenticate)) -> dict:
    store = _store_for(context)
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    if not can_access_document(context, document_id):
        raise HTTPException(status_code=403, detail="문서 접근 권한이 없습니다.")
    audit(context, "document.read", "document", document_id)
    return {**document, "chunks": store.chunks_for_document(document_id)}


@app.delete("/v1/documents/{document_id}", status_code=204)
def delete_document(document_id: str, context: AuthContext = Depends(authenticate)) -> None:
    require_role(context, "manager")
    if not _store_for(context).delete_document(document_id):
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    audit(context, "document.delete", "document", document_id)


@app.get("/v1/documents/{document_id}/versions")
def document_versions(document_id: str, context: AuthContext = Depends(authenticate)) -> dict:
    store = _store_for(context)
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    if not can_access_document(context, document_id):
        raise HTTPException(status_code=403, detail="문서 접근 권한이 없습니다.")
    return {"filename": document["filename"], "versions": store.versions(document["filename"])}


@app.get("/v1/documents/{document_id}/download")
def download_document(document_id: str, context: AuthContext = Depends(authenticate)):
    store = _store_for(context)
    if not can_access_document(context, document_id):
        raise HTTPException(status_code=403, detail="문서 접근 권한이 없습니다.")
    if not hasattr(store, "download"):
        raise HTTPException(status_code=501, detail="원본 다운로드 저장소가 구성되지 않았습니다.")
    try:
        content, url, filename = store.download(document_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.") from exc
    audit(context, "document.download", "document", document_id)
    if url:
        return RedirectResponse(url)
    return Response(content=content, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/v1/search")
def search_documents(request: SearchRequest, context: AuthContext = Depends(authenticate)) -> dict:
    store = _store_for(context)
    vector = None
    model = None
    if request.mode in {"vector", "hybrid"}:
        provider = embedding_provider_from_env()
        vector = provider.embed([request.query])[0]
        model = provider.model
    results = store.search(request.query, request.top_k, vector, model)
    if request.mode == "vector":
        results = [item for item in results if item.get("vector_rank") is not None]
    audit(context, "document.search", "search", details={"query_length": len(request.query), "results": len(results)})
    return {"query": request.query, "mode": request.mode, "results": results}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, context: AuthContext = Depends(authenticate)) -> dict:
    job = PipelineService(get_job_repository()).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    if job.payload.get("workspace_id") not in {None, context.workspace_id}:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return job.to_dict()


@app.post("/v1/sync", status_code=202)
def sync_documents(context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "editor")
    pipeline = get_pipeline()
    try:
        job = pipeline.start(JobType.SYNC_DOCUMENTS, {"workspace_id": context.workspace_id, "user_id": context.user_id})
        if os.getenv("PIPELINE_MODE", "queue") == "inline":
            pipeline.running(job.job_id)
            store = _store_for(context)
            result = store.sync()
            for document_id in result.get("document_ids", []):
                _embed_document(document_id, store)
            job = pipeline.complete(job.job_id, result)
    except PipelinePublishError as exc:
        raise HTTPException(status_code=503, detail="RabbitMQ 연결에 실패했습니다.") from exc
    return {"job_id": job.job_id, "status": job.status, "result": job.result}


@app.get("/v1/me")
def current_user(context: AuthContext = Depends(authenticate)) -> dict:
    return context.__dict__


@app.post("/v1/invitations")
def invite_user(request: InvitationRequest, background_tasks: BackgroundTasks, context: AuthContext = Depends(authenticate)) -> dict:
    token = create_invitation(context, request.email, request.role)
    base_url = os.getenv("PUBLIC_API_URL", "http://localhost:8000")
    join_url = f"{base_url}/join?token={token}"
    email_sent = bool(request.email and os.getenv("SMTP_HOST"))
    if email_sent:
        background_tasks.add_task(send_invitation, request.email, join_url)
    audit(context, "member.invite", "workspace", context.workspace_id, {"email": request.email, "role": request.role})
    return {"invite_token": token, "join_url": join_url, "email_sent": email_sent, "join_command": f"tibero-doc join {token}"}


@app.post("/v1/auth/join")
def join_workspace(request: JoinRequest) -> dict:
    try:
        token, workspace_id = accept_invitation(request.invite_token, request.email, request.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"access_token": token, "workspace_id": workspace_id}


@app.post("/v1/auth/login")
def password_login(request: LoginRequest) -> dict:
    try:
        return login(request.email, request.password, request.workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/v1/auth/refresh")
def refresh_login(request: RefreshRequest) -> dict:
    try:
        return refresh_access_token(request.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/v1/groups")
def create_group(request: GroupRequest, context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "manager")
    with connect() as connection:
        row = connection.execute("INSERT INTO tibero_doc.groups (workspace_id, name, created_by) VALUES (%s, %s, %s) RETURNING group_id", (context.workspace_id, request.name, context.user_id)).fetchone()
    audit(context, "group.create", "group", str(row[0]), {"name": request.name})
    return {"group_id": str(row[0]), "name": request.name}


@app.post("/v1/groups/{group_id}/members")
def add_group_member(group_id: str, request: GroupMemberRequest, context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "manager")
    with connect() as connection:
        cursor = connection.execute("""
            INSERT INTO tibero_doc.group_members (group_id, user_id)
            SELECT g.group_id, m.user_id FROM tibero_doc.groups g
            JOIN tibero_doc.workspace_members m ON m.workspace_id = g.workspace_id AND m.user_id = %s
            WHERE g.group_id=%s AND g.workspace_id=%s ON CONFLICT DO NOTHING
        """, (request.user_id, group_id, context.workspace_id))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")
    return {"status": "added"}


@app.post("/v1/documents/{document_id}/acl")
def grant_document_acl(document_id: str, request: ACLRequest, context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "manager")
    if not _store_for(context).get_document(document_id):
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    with connect() as connection:
        if request.principal_type == "user":
            principal_exists = connection.execute("SELECT 1 FROM tibero_doc.workspace_members WHERE workspace_id=%s AND user_id=%s", (context.workspace_id, request.principal_id)).fetchone()
        else:
            principal_exists = connection.execute("SELECT 1 FROM tibero_doc.groups WHERE workspace_id=%s AND group_id=%s", (context.workspace_id, request.principal_id)).fetchone()
        if not principal_exists:
            raise HTTPException(status_code=400, detail="같은 워크스페이스의 사용자 또는 그룹만 권한을 받을 수 있습니다.")
        connection.execute("INSERT INTO tibero_doc.document_acl (document_id, principal_type, principal_id, permission, granted_by) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (document_id, principal_type, principal_id) DO UPDATE SET permission=EXCLUDED.permission, granted_by=EXCLUDED.granted_by", (document_id, request.principal_type, request.principal_id, request.permission, context.user_id))
        connection.execute("UPDATE tibero_doc.documents SET visibility='restricted' WHERE document_id=%s", (document_id,))
    audit(context, "document.acl.grant", "document", document_id, request.model_dump())
    return {"status": "granted"}


@app.get("/v1/admin/audit-logs")
def audit_logs(limit: int = Query(100, ge=1, le=1000), context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "manager")
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT audit_id, actor_user_id, action, resource_type, resource_id, details, created_at FROM tibero_doc.audit_logs WHERE workspace_id=%s ORDER BY created_at DESC LIMIT %s", (context.workspace_id, limit))
            return {"logs": [dict(row) for row in cursor.fetchall()]}
