from __future__ import annotations

import json
import os
from typing import Any


class PopularDocumentCache:
    """Redis 장애가 본 서비스 장애로 번지지 않는 선택형 인기 문서 캐시."""

    def __init__(self) -> None:
        self.url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        self.threshold = int(os.getenv("DOCUMENT_CACHE_THRESHOLD", "3"))
        self.ttl = int(os.getenv("DOCUMENT_CACHE_TTL_SECONDS", "300"))

    def _client(self):
        if not self.url:
            return None
        try:
            import redis
            return redis.Redis.from_url(self.url, decode_responses=True, socket_timeout=1)
        except Exception:
            return None

    @staticmethod
    def _key(workspace_id: str, document_id: str) -> str:
        return f"tibero-doc:document:{workspace_id}:{document_id}"

    @staticmethod
    def _popularity_key(workspace_id: str) -> str:
        return f"tibero-doc:popular:{workspace_id}"

    def get(self, workspace_id: str, document_id: str) -> dict[str, Any] | None:
        client = self._client()
        if not client:
            return None
        try:
            value = client.get(self._key(workspace_id, document_id))
            return json.loads(value) if value else None
        except Exception:
            return None

    def record_and_cache(self, workspace_id: str, document_id: str, value: dict[str, Any]) -> int:
        client = self._client()
        if not client:
            return 0
        try:
            score = int(client.zincrby(self._popularity_key(workspace_id), 1, document_id))
            if score >= self.threshold:
                client.setex(self._key(workspace_id, document_id), self.ttl, json.dumps(value, default=str))
            return score
        except Exception:
            return 0

    def invalidate(self, workspace_id: str, document_id: str) -> None:
        client = self._client()
        if client:
            try:
                client.delete(self._key(workspace_id, document_id))
            except Exception:
                pass

    def status(self) -> dict[str, Any]:
        client = self._client()
        if not client:
            return {"enabled": False, "status": "not-configured"}
        try:
            return {"enabled": True, "status": "healthy" if client.ping() else "unavailable", "threshold": self.threshold, "ttl_seconds": self.ttl}
        except Exception as exc:
            return {"enabled": True, "status": "unavailable", "detail": str(exc)}


document_cache = PopularDocumentCache()
