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
from services.api.auth import AuthContext, accept_invitation, audit, authenticate, can_access_document, create_invitation, issue_token, login, refresh_access_token, require_role
from services.api.agent import answer_question
from services.api.cache import document_cache
from services.api.email_service import send_invitation
from services.api.rate_limit import RateLimitMiddleware
from packages.core.database import connect
from packages.core.knowledge_graph import KnowledgeGraphService
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
    mode: str = Field(default="hybrid", pattern="^(keyword|vector|graph|hybrid)$")


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


class AgentRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class RoleRequest(BaseModel):
    role: str = Field(pattern="^(viewer|editor|manager|owner)$")


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


def _index_graph(document_id: str, workspace_id: str, store: DocumentStore) -> dict:
    return KnowledgeGraphService().index_document(workspace_id, document_id, store.chunks_for_document(document_id))


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
            graph = _index_graph(record.document_id, context.workspace_id, store)
            embedding = _embed_document(record.document_id, store)
            job = pipeline.complete(job.job_id, {
                "document_id": record.document_id, "filename": record.filename,
                "version": record.version, "chunks": record.chunk_count,
                **embedding, "graph": graph,
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
    # 캐시는 성능 계층일 뿐 권한 계층이 아니다. 매 요청마다 OpenSQL ACL을 먼저 확인한다.
    if not can_access_document(context, document_id):
        raise HTTPException(status_code=403, detail="문서 접근 권한이 없습니다.")
    cached = document_cache.get(context.workspace_id, document_id)
    if cached is not None:
        audit(context, "document.read.cached", "document", document_id)
        return {**cached, "cache": "hit"}
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    result = {**document, "chunks": store.chunks_for_document(document_id)}
    popularity = document_cache.record_and_cache(context.workspace_id, document_id, result)
    audit(context, "document.read", "document", document_id, {"popularity": popularity})
    return {**result, "cache": "miss", "popularity": popularity}


@app.delete("/v1/documents/{document_id}", status_code=204)
def delete_document(document_id: str, context: AuthContext = Depends(authenticate)) -> None:
    require_role(context, "manager")
    if not _store_for(context).delete_document(document_id):
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    document_cache.invalidate(context.workspace_id, document_id)
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


@app.get("/v1/documents/{document_id}/graph")
def document_graph(document_id: str, context: AuthContext = Depends(authenticate)) -> dict:
    if not can_access_document(context, document_id):
        raise HTTPException(status_code=403, detail="문서 접근 권한이 없습니다.")
    graph = KnowledgeGraphService().document_graph(context.workspace_id, document_id)
    return {"document_id": document_id, **graph}


@app.post("/v1/graph/reindex")
def reindex_knowledge_graph(context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "manager")
    store = _store_for(context)
    results = []
    for document in store.list_documents(10000, 0):
        results.append({
            "document_id": document["document_id"],
            **_index_graph(document["document_id"], context.workspace_id, store),
        })
    audit(context, "graph.reindex", "workspace", context.workspace_id, {"documents": len(results)})
    return {"documents": len(results), "results": results}


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
    elif request.mode == "graph":
        results = [item for item in results if item.get("graph_rank") is not None]
    elif request.mode == "keyword":
        results = [item for item in results if item.get("keyword_rank") is not None]
    audit(context, "document.search", "search", details={"query_length": len(request.query), "results": len(results)})
    return {"query": request.query, "mode": request.mode, "results": results}


@app.post("/v1/agent/ask")
def ask_agent(request: AgentRequest, context: AuthContext = Depends(authenticate)) -> dict:
    store = _store_for(context)
    provider = embedding_provider_from_env()
    vector = provider.embed([request.question])[0]
    results = store.search(request.question, request.top_k, vector, provider.model)
    answer, answer_provider = answer_question(request.question, results)
    citations = [
        {"index": index, "document_id": item["document_id"], "filename": item["filename"], "chunk_index": item["chunk_index"], "score": item.get("score"), "entities": item.get("entities", []), "graph_rank": item.get("graph_rank")}
        for index, item in enumerate(results, 1)
    ]
    audit(context, "agent.ask", "search", details={"question_length": len(request.question), "results": len(results), "provider": answer_provider})
    return {"question": request.question, "answer": answer, "provider": answer_provider, "citations": citations}


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
                _index_graph(document_id, context.workspace_id, store)
                _embed_document(document_id, store)
            job = pipeline.complete(job.job_id, result)
    except PipelinePublishError as exc:
        raise HTTPException(status_code=503, detail="RabbitMQ 연결에 실패했습니다.") from exc
    return {"job_id": job.job_id, "status": job.status, "result": job.result}


@app.get("/v1/me")
def current_user(context: AuthContext = Depends(authenticate)) -> dict:
    return context.__dict__


@app.get("/v1/stats")
def workspace_stats(context: AuthContext = Depends(authenticate)) -> dict:
    """현재 인증 사용자가 볼 수 있는 워크스페이스의 문서 통계를 반환한다."""
    return _store_for(context).stats()


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


@app.get("/v1/groups")
def list_groups(context: AuthContext = Depends(authenticate)) -> dict:
    with connect() as connection:
        rows = connection.execute(
            """SELECT g.group_id, g.name, count(gm.user_id) FROM tibero_doc.groups g
                 LEFT JOIN tibero_doc.group_members gm USING(group_id)
                WHERE g.workspace_id=%s GROUP BY g.group_id, g.name ORDER BY g.name""",
            (context.workspace_id,),
        ).fetchall()
    return {"groups": [{"group_id": str(row[0]), "name": row[1], "member_count": row[2]} for row in rows]}


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


@app.delete("/v1/groups/{group_id}/members/{user_id}", status_code=204)
def remove_group_member(group_id: str, user_id: str, context: AuthContext = Depends(authenticate)) -> None:
    require_role(context, "manager")
    with connect() as connection:
        cursor = connection.execute(
            """DELETE FROM tibero_doc.group_members gm USING tibero_doc.groups g
                WHERE gm.group_id=g.group_id AND gm.group_id=%s AND gm.user_id=%s AND g.workspace_id=%s""",
            (group_id, user_id, context.workspace_id),
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="그룹 멤버를 찾을 수 없습니다.")
    audit(context, "group.member.remove", "group", group_id, {"user_id": user_id})


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
    document_cache.invalidate(context.workspace_id, document_id)
    audit(context, "document.acl.grant", "document", document_id, request.model_dump())
    return {"status": "granted"}


@app.get("/v1/documents/{document_id}/acl")
def list_document_acl(document_id: str, context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "manager")
    if not _store_for(context).get_document(document_id):
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    with connect() as connection:
        rows = connection.execute(
            "SELECT principal_type, principal_id, permission, granted_by, created_at FROM tibero_doc.document_acl WHERE document_id=%s ORDER BY created_at",
            (document_id,),
        ).fetchall()
    return {"acl": [{"principal_type": r[0], "principal_id": str(r[1]), "permission": r[2], "granted_by": str(r[3]), "created_at": r[4]} for r in rows]}


@app.delete("/v1/documents/{document_id}/acl/{principal_type}/{principal_id}", status_code=204)
def revoke_document_acl(document_id: str, principal_type: str, principal_id: str, context: AuthContext = Depends(authenticate)) -> None:
    require_role(context, "manager")
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM tibero_doc.document_acl WHERE document_id=%s AND principal_type=%s AND principal_id=%s",
            (document_id, principal_type, principal_id),
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="ACL 항목을 찾을 수 없습니다.")
    document_cache.invalidate(context.workspace_id, document_id)
    audit(context, "document.acl.revoke", "document", document_id, {"principal_type": principal_type, "principal_id": principal_id})


@app.get("/v1/workspaces")
def list_workspaces(context: AuthContext = Depends(authenticate)) -> dict:
    with connect() as connection:
        rows = connection.execute(
            """SELECT w.workspace_id, w.name, w.slug, o.name, m.role
                 FROM tibero_doc.workspace_members m JOIN tibero_doc.workspaces w USING(workspace_id)
                 JOIN tibero_doc.organizations o USING(organization_id)
                WHERE m.user_id=%s ORDER BY o.name, w.name""",
            (context.user_id,),
        ).fetchall()
    return {"workspaces": [{"workspace_id": str(r[0]), "name": r[1], "slug": r[2], "organization": r[3], "role": r[4], "current": str(r[0]) == context.workspace_id} for r in rows]}


@app.post("/v1/workspaces/{workspace_id}/switch")
def switch_workspace(workspace_id: str, context: AuthContext = Depends(authenticate)) -> dict:
    with connect() as connection:
        member = connection.execute("SELECT 1 FROM tibero_doc.workspace_members WHERE workspace_id=%s AND user_id=%s", (workspace_id, context.user_id)).fetchone()
    if not member:
        raise HTTPException(status_code=404, detail="가입된 워크스페이스를 찾을 수 없습니다.")
    return {"access_token": issue_token(context.user_id, workspace_id, "workspace-switch"), "workspace_id": workspace_id}


@app.get("/v1/users")
def list_users(context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "manager")
    with connect() as connection:
        rows = connection.execute(
            """SELECT u.user_id, u.email, u.display_name, u.status, m.role, m.joined_at
                 FROM tibero_doc.workspace_members m JOIN tibero_doc.users u USING(user_id)
                WHERE m.workspace_id=%s ORDER BY u.email""",
            (context.workspace_id,),
        ).fetchall()
    return {"users": [{"user_id": str(r[0]), "email": r[1], "display_name": r[2], "status": r[3], "role": r[4], "joined_at": r[5]} for r in rows]}


@app.patch("/v1/users/{user_id}/role")
def change_user_role(user_id: str, request: RoleRequest, context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "owner")
    with connect() as connection:
        cursor = connection.execute("UPDATE tibero_doc.workspace_members SET role=%s WHERE workspace_id=%s AND user_id=%s", (request.role, context.workspace_id, user_id))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    audit(context, "user.role.change", "user", user_id, {"role": request.role})
    return {"status": "updated", "role": request.role}


@app.post("/v1/users/{user_id}/disable")
def disable_user(user_id: str, context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "owner")
    if user_id == context.user_id:
        raise HTTPException(status_code=400, detail="자기 계정은 비활성화할 수 없습니다.")
    with connect() as connection:
        cursor = connection.execute("UPDATE tibero_doc.users SET status='disabled' WHERE user_id=%s", (user_id,))
        connection.execute("UPDATE tibero_doc.api_tokens SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL", (user_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    audit(context, "user.disable", "user", user_id)
    return {"status": "disabled"}


@app.get("/v1/admin/storage-status")
def storage_status(context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "manager")
    return {"object_storage": os.getenv("OBJECT_STORAGE", "local"), "redis_cache": document_cache.status(), "stats": _store_for(context).stats()}


@app.get("/v1/admin/retention-plan")
def retention_plan(
    hot_days: int = Query(30, ge=1), cold_days: int = Query(180, ge=2),
    delete_days: int = Query(365, ge=3), context: AuthContext = Depends(authenticate),
) -> dict:
    """파괴 작업 없이 문서 수명주기 후보만 분류한다."""
    require_role(context, "manager")
    if not hot_days < cold_days < delete_days:
        raise HTTPException(status_code=400, detail="hot_days < cold_days < delete_days 순서여야 합니다.")
    with connect() as connection:
        rows = connection.execute(
            """SELECT document_id, filename, updated_at, metadata,
                      extract(day from now() - updated_at)::int AS age_days
                 FROM tibero_doc.documents WHERE workspace_id=%s ORDER BY updated_at""",
            (context.workspace_id,),
        ).fetchall()
    buckets = {"hot": [], "warm": [], "cold": [], "delete_candidate": [], "legal_hold": []}
    for document_id, filename, updated_at, metadata, age_days in rows:
        item = {"document_id": document_id, "filename": filename, "updated_at": updated_at, "age_days": age_days}
        if (metadata or {}).get("legal_hold"):
            bucket = "legal_hold"
        elif age_days <= hot_days:
            bucket = "hot"
        elif age_days <= cold_days:
            bucket = "warm"
        elif age_days <= delete_days:
            bucket = "cold"
        else:
            bucket = "delete_candidate"
        buckets[bucket].append(item)
    return {"policy": {"hot_days": hot_days, "cold_days": cold_days, "delete_days": delete_days, "automatic_delete": False}, "buckets": buckets}


@app.get("/v1/admin/audit-logs")
def audit_logs(limit: int = Query(100, ge=1, le=1000), context: AuthContext = Depends(authenticate)) -> dict:
    require_role(context, "manager")
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT audit_id, actor_user_id, action, resource_type, resource_id, details, created_at FROM tibero_doc.audit_logs WHERE workspace_id=%s ORDER BY created_at DESC LIMIT %s", (context.workspace_id, limit))
            return {"logs": [dict(row) for row in cursor.fetchall()]}
