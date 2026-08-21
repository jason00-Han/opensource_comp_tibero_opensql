from __future__ import annotations

from datetime import datetime, timedelta
import os

from airflow.decorators import dag, task
from airflow.providers.http.hooks.http import HttpHook


@dag(schedule="0 2 * * *", start_date=datetime(2026, 1, 1), catchup=False,
     default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
     tags=["tibero-doc"])
def tibero_doc_maintenance():
    @task
    def reindex_embeddings():
        token = os.environ["TIBERO_DOC_MAINTENANCE_TOKEN"]
        response = HttpHook(method="POST", http_conn_id="tibero_doc_api").run(
            "/v1/embeddings/reindex", headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        return response.json()

    @task
    def move_storage_tiers():
        token = os.environ["TIBERO_DOC_MAINTENANCE_TOKEN"]
        response = HttpHook(method="POST", http_conn_id="tibero_doc_api").run(
            "/v1/admin/storage/lifecycle/run", headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        return response.json()

    reindex_embeddings() >> move_storage_tiers()


tibero_doc_maintenance()
