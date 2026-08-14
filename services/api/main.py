from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from packages.core.pipeline import (
    JobPublisher,
    JobType,
    JsonJobRepository,
    PipelinePublishError,
    PipelineService,
    RabbitMQPublisher,
)

from services.api.store import DocumentStore



app = FastAPI(
    title="Tibero Doc API",
    version="0.1.0",
    description="CLI 개발을 위한 로컬 문서 수집 및 검색 API",
)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)


def get_store() -> DocumentStore:
    return DocumentStore()

def get_job_repository() -> JsonJobRepository:
    return JsonJobRepository()

def get_publisher() -> JobPublisher:
    return RabbitMQPublisher()

def get_pipeline() -> PipelineService:
    return PipelineService(get_job_repository(), get_publisher())

@app.get("/")
def root() -> dict:
    return {
        "name": "Tibero Doc API",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict:
    try:
        stats = get_store().stats()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "status": "healthy",
        "components": {
            "api": "healthy",
            "local_storage": "healthy",
            "keyword_index": "healthy",
        },
        **stats,
    }


@app.post("/v1/documents", status_code=201)
async def ingest_document(file: UploadFile = File(...)) -> dict:
    try:
        record = get_store().ingest_bytes(file.filename or "document", await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        job = get_pipeline().start(
            JobType.INDEX_DOCUMENT,
            {"filename": stored.filename, "document_id": stored.document_id},
        )
    except PipelinePublishError as exc:
        raise HTTPException(status_code=503, detail="RabbitMQ에 연결할 수 없습니다.") from exc
    return {
        "job_id": job.job_id,
        "document_id": stored.document_id,
        "filename": stored.filename,
        "size": stored.size,
        "status": "queued",
    }


@app.post("/v1/search")
def search_documents(request: SearchRequest) -> dict:
    return {
        "query": request.query,
        "results": get_store().search(request.query, request.top_k),
    }

@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = get_pipeline().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}")
    return job.to_dict()

@app.post("/v1/sync")
def sync_documents() -> dict:
    try:
        job = get_pipeline().start(JobType.SYNC_DOCUMENTS, {})
    except PipelinePublishError as exc:
        raise HTTPException(status_code=503, detail="RabbitMQ에 연결할 수 없습니다.") from exc
    return {"job_id": job.job_id, "status": job.status}
