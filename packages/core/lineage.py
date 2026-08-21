from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from packages.core.database import connect, database_dsn


def record_lineage(operation: str, *, workspace_id: str | None = None,
                   document_id: str | None = None, source_uri: str | None = None,
                   input_version: int | None = None, output_model: str | None = None,
                   job_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    dsn = database_dsn()
    if not dsn:
        return
    with connect(dsn) as connection:
        connection.execute(
            """INSERT INTO tibero_doc.data_lineage_events
               (workspace_id,document_id,source_uri,operation,input_version,output_model,job_id,metadata)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (workspace_id, document_id, source_uri, operation, input_version,
             output_model, job_id, Jsonb(metadata or {})),
        )
