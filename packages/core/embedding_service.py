from __future__ import annotations

import json
import hashlib
import math
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from filelock import FileLock
import httpx

from packages.core.database import connect, database_dsn, vector_literal


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


class LocalHashEmbeddingProvider:
    """Dependency-free deterministic embedding for an offline demo.

    It hashes words and character trigrams into a fixed vector.  It is useful
    for running the whole platform without an API key; use an OpenAI-compatible
    model for production-quality semantic retrieval.
    """

    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions or int(os.getenv("EMBEDDING_DIMENSIONS", "384"))
        self._model = os.getenv("EMBEDDING_MODEL", f"local-hash-{self.dimensions}")

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        normalized = re.sub(r"\s+", " ", text.lower()).strip()
        words = re.findall(r"[0-9a-zA-Z가-힣]+", normalized)
        features = words + [
            normalized[index:index + 3]
            for index in range(max(0, len(normalized) - 2))
            if " " not in normalized[index:index + 3]
        ]
        vector = [0.0] * self.dimensions
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            position = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[position] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


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
        with FileLock(str(self.lock_path)):
            yield

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


class OpenSQLEmbeddingRepository:
    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or database_dsn()
        if not self.dsn:
            raise RuntimeError("TIBERO_DOC_DSN is not configured")

    def replace_document(self, document_id: str, embeddings: list[ChunkEmbedding]) -> None:
        with connect(self.dsn) as connection:
            connection.execute(
                "DELETE FROM tibero_doc.chunk_embeddings WHERE document_id = %s",
                (document_id,),
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO tibero_doc.chunk_embeddings
                        (document_id, chunk_index, model, dimensions, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    """,
                    [
                        (
                            item.document_id, item.chunk_index, item.model,
                            len(item.vector), vector_literal(item.vector),
                        )
                        for item in embeddings
                    ],
                )


def embedding_provider_from_env() -> EmbeddingProvider:
    provider = os.getenv("EMBEDDING_PROVIDER", "local").lower()
    if provider in {"openai", "ollama", "http"}:
        return OpenAICompatibleEmbeddingProvider()
    if provider in {"local", "hash"}:
        return LocalHashEmbeddingProvider()
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {provider}")


def embedding_repository_from_env() -> EmbeddingRepository:
    return OpenSQLEmbeddingRepository() if database_dsn() else JsonEmbeddingRepository()


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
