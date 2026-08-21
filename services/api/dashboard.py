from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from psycopg.rows import dict_row

from packages.core.database import connect, database_dsn
from services.api.auth import AuthContext


def _component(error: Exception | str) -> dict:
    message = str(error)
    for secret in (os.getenv("RABBITMQ_PASSWORD"), os.getenv("TIBERO_DOC_DSN")):
        if secret: message = message.replace(secret, "***")
    return {"status": "unavailable", "error": message[:200]}


def _database(context: AuthContext) -> dict:
    if not database_dsn():
        return {"status": "not_configured", "documents": 0, "users": 1, "groups": 0,
                "chunks": 0, "embeddings": 0, "entities": 0, "relationships": 0,
                "pipeline": {}, "recent_documents": [], "memberships": {"nodes": [], "edges": []}}
    try:
        with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
            counts = cursor.execute("""
                SELECT
                  (SELECT count(*) FROM tibero_doc.documents WHERE workspace_id=%s) documents,
                  (SELECT count(*) FROM tibero_doc.workspace_members WHERE workspace_id=%s) users,
                  (SELECT count(*) FROM tibero_doc.groups WHERE workspace_id=%s) groups,
                  (SELECT count(*) FROM tibero_doc.chunks c JOIN tibero_doc.documents d USING(document_id) WHERE d.workspace_id=%s) chunks,
                  (SELECT count(*) FROM tibero_doc.chunk_embeddings e JOIN tibero_doc.documents d USING(document_id) WHERE d.workspace_id=%s) embeddings,
                  (SELECT count(*) FROM tibero_doc.entities WHERE workspace_id=%s) entities,
                  (SELECT count(*) FROM tibero_doc.relationships WHERE workspace_id=%s) relationships,
                  (SELECT count(*) FROM tibero_doc.outbox_events WHERE published_at IS NULL) outbox_pending
            """, (context.workspace_id,) * 7).fetchone()
            pipeline = cursor.execute("""SELECT status,count(*) count FROM tibero_doc.pipeline_jobs
                WHERE payload->>'workspace_id'=%s GROUP BY status""", (context.workspace_id,)).fetchall()
            documents = cursor.execute("""SELECT d.document_id,d.filename,d.version,d.chunk_count,d.size_bytes,
                       d.visibility,d.updated_at,u.display_name owner,
                       EXISTS(SELECT 1 FROM tibero_doc.chunk_embeddings e WHERE e.document_id=d.document_id) embedded
                  FROM tibero_doc.documents d LEFT JOIN tibero_doc.users u ON u.user_id=d.owner_user_id
                 WHERE d.workspace_id=%s ORDER BY d.updated_at DESC LIMIT 12""", (context.workspace_id,)).fetchall()
            users = cursor.execute("""SELECT u.user_id,u.display_name,u.email,u.status,m.role
                  FROM tibero_doc.workspace_members m JOIN tibero_doc.users u USING(user_id)
                 WHERE m.workspace_id=%s ORDER BY u.display_name""", (context.workspace_id,)).fetchall()
            groups = cursor.execute("SELECT group_id,name FROM tibero_doc.groups WHERE workspace_id=%s ORDER BY name",
                                    (context.workspace_id,)).fetchall()
            memberships = cursor.execute("""SELECT gm.user_id,gm.group_id FROM tibero_doc.group_members gm
                JOIN tibero_doc.groups g USING(group_id) WHERE g.workspace_id=%s""", (context.workspace_id,)).fetchall()
            recent_jobs = cursor.execute("""SELECT job_id,job_type,stage,status,error,updated_at
                  FROM tibero_doc.pipeline_jobs WHERE payload->>'workspace_id'=%s
                 ORDER BY updated_at DESC LIMIT 10""", (context.workspace_id,)).fetchall()
        nodes = ([{"id": str(row["user_id"]), "label": row["display_name"], "kind": "user", "detail": row["role"]} for row in users] +
                 [{"id": str(row["group_id"]), "label": row["name"], "kind": "group"} for row in groups])
        return {"status": "healthy", **dict(counts), "pipeline": {r["status"]: r["count"] for r in pipeline},
                "recent_documents": [dict(r) for r in documents], "recent_jobs": [dict(r) for r in recent_jobs],
                "memberships": {"nodes": nodes, "edges": [{"source": str(r["user_id"]), "target": str(r["group_id"])} for r in memberships]}}
    except Exception as exc:
        return _component(exc)


def _workers() -> dict:
    url = os.getenv("REDIS_URL")
    if not url: return {"status": "not_configured", "items": []}
    try:
        import redis
        client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=1)
        items = []
        for key in client.scan_iter("tibero-doc:worker:*"):
            value = client.get(key)
            if value: items.append(json.loads(value))
        return {"status": "healthy", "online": len(items), "items": sorted(items, key=lambda x: x["worker_id"])}
    except Exception as exc: return _component(exc) | {"items": []}


def _rabbitmq() -> dict:
    url = os.getenv("RABBITMQ_MANAGEMENT_URL", "http://127.0.0.1:15672").rstrip("/")
    user = os.getenv("RABBITMQ_USER", "guest")
    password = os.getenv("RABBITMQ_PASSWORD", "guest")
    try:
        response = httpx.get(f"{url}/api/queues/%2F", auth=(user, password), timeout=2)
        response.raise_for_status()
        queues = []
        for row in response.json():
            if not any(row["name"] == prefix or row["name"].startswith(prefix + ".")
                       for prefix in ("tibero-doc.ingest", "tibero-doc.embedding", "tibero-doc.sync")):
                continue
            queues.append({"name": row["name"], "ready": row.get("messages_ready", 0),
                           "processing": row.get("messages_unacknowledged", 0),
                           "consumers": row.get("consumers", 0),
                           "rate": row.get("message_stats", {}).get("ack_details", {}).get("rate", 0)})
        return {"status": "healthy", "queues": queues,
                "ready": sum(q["ready"] for q in queues),
                "processing": sum(q["processing"] for q in queues),
                "retry": sum(q["ready"] for q in queues if q["name"].endswith(".retry")),
                "dlq": sum(q["ready"] for q in queues if q["name"].endswith(".dlq"))}
    except Exception as exc: return _component(exc) | {"queues": []}


def _nodes() -> dict:
    configured = [item.strip() for item in os.getenv("PATRONI_API_URLS", "").split(",") if item.strip()]
    if not configured: return {"status": "not_configured", "items": []}
    items = []
    for index, url in enumerate(configured, 1):
        try:
            response = httpx.get(url.rstrip("/") + "/patroni", timeout=2)
            response.raise_for_status(); data = response.json()
            items.append({"name": data.get("name", f"db{index}"), "role": data.get("role", "unknown"),
                          "state": data.get("state", "unknown"), "timeline": data.get("timeline"),
                          "lag": data.get("replication", {}).get("lag", 0), "status": "healthy"})
        except Exception as exc:
            items.append({"name": f"db{index}", "role": "unknown", "state": "unreachable", "status": "unavailable", "error": str(exc)[:100]})
    healthy = sum(item["status"] == "healthy" for item in items)
    return {"status": "healthy" if healthy == len(items) else "warning", "healthy": healthy, "total": len(items), "items": items}


def _prometheus() -> dict:
    url = os.getenv("PROMETHEUS_URL", "http://127.0.0.1:9090").rstrip("/")
    queries = {"requests_per_second": "sum(rate(tibero_doc_http_requests_total[5m]))",
               "p95_seconds": "histogram_quantile(0.95,sum(rate(tibero_doc_http_request_duration_seconds_bucket[5m])) by (le))",
               "worker_jobs_per_second": "sum(rate(tibero_doc_worker_jobs_total[5m]))"}
    try:
        values = {}
        for key, query in queries.items():
            data = httpx.get(f"{url}/api/v1/query", params={"query": query}, timeout=2).json()
            result = data.get("data", {}).get("result", [])
            values[key] = float(result[0]["value"][1]) if result else 0
        return {"status": "healthy", **values}
    except Exception as exc: return _component(exc)


def _loki(limit: int = 30) -> dict:
    url = os.getenv("LOKI_URL", "http://127.0.0.1:3100").rstrip("/")
    try:
        response = httpx.get(f"{url}/loki/api/v1/query_range", params={"query": '{service=~"tibero-doc-api|worker-.*"}',
            "limit": limit, "direction": "backward", "end": time.time_ns()}, timeout=3)
        response.raise_for_status(); entries = []
        for stream in response.json().get("data", {}).get("result", []):
            for timestamp, line in stream.get("values", []):
                try: item = json.loads(line)
                except json.JSONDecodeError: item = {"message": line}
                item["timestamp"] = datetime.fromtimestamp(int(timestamp) / 1e9, UTC).isoformat()
                entries.append(item)
        entries.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"status": "healthy", "items": entries[:limit]}
    except Exception as exc: return _component(exc) | {"items": []}


def dashboard_overview(context: AuthContext) -> dict:
    components = {"opensql": _database(context), "workers": _workers(), "rabbitmq": _rabbitmq(),
                  "nodes": _nodes(), "prometheus": _prometheus(), "logs": _loki()}
    warning = (components["rabbitmq"].get("dlq", 0) > 0 or
               any(c.get("status") in {"warning", "unavailable"} for c in components.values()))
    return {"status": "warning" if warning else "healthy", "generated_at": datetime.now(UTC).isoformat(), **components}
