from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    _memory: dict[str, list[float]] = defaultdict(list)
    _lock = threading.Lock()

    def __init__(self, app) -> None:
        super().__init__(app)
        self.limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
        self.redis = None
        if os.getenv("REDIS_URL"):
            try:
                import redis
                self.redis = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
                self.redis.ping()
            except Exception:
                self.redis = None

    async def dispatch(self, request, call_next):
        if request.url.path.startswith(("/health", "/static")):
            return await call_next(request)
        identity = request.headers.get("authorization") or (request.client.host if request.client else "unknown")
        key = "rate:" + hashlib.sha256(identity.encode()).hexdigest()
        allowed, remaining = self._consume(key)
        if not allowed:
            return JSONResponse({"detail": "요청이 너무 많습니다. 잠시 후 다시 시도하세요."}, status_code=429, headers={"Retry-After": "60"})
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        return response

    def _consume(self, key: str) -> tuple[bool, int]:
        if self.redis:
            bucket = f"{key}:{int(time.time() // 60)}"
            count = self.redis.incr(bucket)
            if count == 1:
                self.redis.expire(bucket, 70)
            return count <= self.limit, self.limit - count
        now = time.time()
        with self._lock:
            self._memory[key] = [stamp for stamp in self._memory[key] if stamp > now - 60]
            self._memory[key].append(now)
            count = len(self._memory[key])
        return count <= self.limit, self.limit - count
