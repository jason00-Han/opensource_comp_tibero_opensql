from __future__ import annotations

import json
import logging
import os
import platform
import queue
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from prometheus_client import Counter, Histogram, start_http_server

JOBS = Counter("tibero_doc_worker_jobs_total", "Worker jobs", ["worker_type", "result"])
JOB_DURATION = Histogram("tibero_doc_worker_job_duration_seconds", "Worker job duration", ["worker_type"])


class WorkerHeartbeat:
    """Stores ephemeral worker state in Redis with a TTL; absence means offline."""

    def __init__(self, worker_type: str) -> None:
        self.worker_type = worker_type
        self.worker_id = os.getenv("WORKER_ID", f"{worker_type}-{platform.node()}-{os.getpid()}")
        self.key = f"tibero-doc:worker:{self.worker_id}"
        self.interval = int(os.getenv("WORKER_HEARTBEAT_SECONDS", "10"))
        self.ttl = int(os.getenv("WORKER_HEARTBEAT_TTL", "30"))
        self.state: dict[str, Any] = {"status": "idle", "current_job_id": None,
                                      "processed_total": 0, "failed_total": 0}
        self.redis = None
        if os.getenv("REDIS_URL"):
            try:
                import redis
                self.redis = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
                self.redis.ping()
            except Exception:
                self.redis = None

    def start(self) -> None:
        metrics_port = os.getenv("WORKER_METRICS_PORT")
        if metrics_port:
            try: start_http_server(int(metrics_port))
            except OSError: pass
        if not self.redis:
            return
        self._write()
        threading.Thread(target=self._loop, daemon=True, name=f"heartbeat-{self.worker_id}").start()

    def processing(self, job_id: str) -> float:
        self.state.update(status="processing", current_job_id=job_id)
        self._write()
        return time.perf_counter()

    def finished(self, started: float, success: bool) -> None:
        key = "processed_total" if success else "failed_total"
        self.state[key] += 1
        self.state.update(status="idle", current_job_id=None, last_duration_seconds=time.perf_counter() - started)
        JOBS.labels(self.worker_type, "success" if success else "failed").inc()
        JOB_DURATION.labels(self.worker_type).observe(time.perf_counter() - started)
        self._write()

    def _loop(self) -> None:
        while True:
            time.sleep(self.interval)
            self._write()

    def _write(self) -> None:
        if not self.redis:
            return
        value = {**self.state, "worker_id": self.worker_id, "worker_type": self.worker_type,
                 "hostname": platform.node(), "pid": os.getpid(),
                 "last_heartbeat": datetime.now(UTC).isoformat()}
        try:
            self.redis.setex(self.key, self.ttl, json.dumps(value))
        except Exception:
            pass


class LokiHandler(logging.Handler):
    """Non-blocking JSON log shipper; application work never waits for Loki."""

    def __init__(self, url: str, service: str) -> None:
        super().__init__()
        self.url = url.rstrip("/") + "/loki/api/v1/push"
        self.service = service
        self.buffer: queue.Queue[dict] = queue.Queue(maxsize=2000)
        threading.Thread(target=self._send_loop, daemon=True, name="loki-log-shipper").start()

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(("httpx", "httpcore")):
            return
        try:
            entry = {"level": record.levelname, "logger": record.name, "message": self.format(record),
                     "service": self.service, "trace_id": getattr(record, "trace_id", uuid.uuid4().hex[:12])}
            self.buffer.put_nowait(entry)
        except Exception:
            pass

    def _send_loop(self) -> None:
        while True:
            first = self.buffer.get()
            batch = [first]
            while len(batch) < 100:
                try: batch.append(self.buffer.get_nowait())
                except queue.Empty: break
            values = [[str(time.time_ns()), json.dumps(item, ensure_ascii=False)] for item in batch]
            try:
                httpx.post(self.url, json={"streams": [{"stream": {"service": self.service}, "values": values}]}, timeout=2)
            except Exception:
                pass


def configure_loki_logging(service: str) -> None:
    url = os.getenv("LOKI_URL")
    root = logging.getLogger()
    if url and not any(isinstance(handler, LokiHandler) for handler in root.handlers):
        root.addHandler(LokiHandler(url, service))
