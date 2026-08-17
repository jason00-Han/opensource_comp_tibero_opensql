from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import fcntl
import httpx


@dataclass(frozen=True)
class ChunkEmbedding:
    document_id: str
    chunk_index: int
    model: str
    vector: list[float]


class EmbeddingProvider(Protocol):
    @property
    def model(self) -> str: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingRepository(Protocol):
    def replace_document(self, document_id: str, embeddings: list[ChunkEmbedding]) -> None: ...


class OpenAICompatibleEmbeddingProvider:
    """Embedding client for an OpenAI-compatible `/embeddings` HTTP endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("EMBEDDING_API_URL", "http://127.0.0.1:11434/v1")).rstrip("/")
        self._model = model or os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
        self.api_key = api_key if api_key is not None else os.getenv("EMBEDDING_API_KEY")
        self.timeout = timeout
        self.client = client

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        request = self.client.post if self.client else httpx.post
        response = request(
            f"{self.base_url}/embeddings",
            headers=headers,
            json={"model": self.model, "input": texts},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        vectors = [item["embedding"] for item in data]
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding API returned an unexpected vector count")
        return vectors


class JsonEmbeddingRepository:
    """Local MVP vector repository; replace with the OpenSQL implementation in deployment."""

    def __init__(self, data_dir: Path | None = None) -> None:
        configured = os.getenv("TIBERO_DOC_DATA_DIR")
        self.data_dir = data_dir or (Path(configured) if configured else Path.home() / ".tibero-doc" / "data")
        self.path = self.data_dir / "embeddings.json"
        self.lock_path = self.data_dir / "embeddings.lock"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _locked(self):
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def replace_document(self, document_id: str, embeddings: list[ChunkEmbedding]) -> None:
        with self._locked():
            records = [item for item in self._load() if item["document_id"] != document_id]
            records.extend({
                "document_id": item.document_id,
                "chunk_index": item.chunk_index,
                "model": item.model,
                "vector": item.vector,
            } for item in embeddings)
            descriptor, temporary_name = tempfile.mkstemp(dir=self.data_dir, prefix="embeddings-", suffix=".tmp")
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                    json.dump(records, temporary, ensure_ascii=False)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                Path(temporary_name).replace(self.path)
            finally:
                Path(temporary_name).unlink(missing_ok=True)


class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider, repository: EmbeddingRepository) -> None:
        self.provider = provider
        self.repository = repository

    def embed_document(self, document_id: str, chunks: list[dict]) -> dict:
        vectors = self.provider.embed([chunk["content"] for chunk in chunks])
        embeddings = [
            ChunkEmbedding(document_id, chunk["chunk_index"], self.provider.model, vector)
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self.repository.replace_document(document_id, embeddings)
        return {"document_id": document_id, "embeddings": len(embeddings), "model": self.provider.model}
