"""Checksum-verified SQL migration runner for OpenSQL."""
from __future__ import annotations

import hashlib
from pathlib import Path

from packages.core.database import connect, database_dsn


def migrate(directory: Path = Path("infra/opensql/migrations")) -> None:
    dsn = database_dsn()
    if not dsn:
        raise SystemExit("TIBERO_DOC_DSN is required")
    with connect(dsn) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS tibero_doc")
        connection.execute("""CREATE TABLE IF NOT EXISTS tibero_doc.schema_migrations
          (version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())""")
        applied = dict(connection.execute("SELECT version,checksum FROM tibero_doc.schema_migrations").fetchall())
        for path in sorted(directory.glob("*.sql")):
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            if path.name in applied:
                if applied[path.name] != checksum:
                    raise RuntimeError(f"migration checksum changed: {path.name}")
                continue
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute("INSERT INTO tibero_doc.schema_migrations(version,checksum) VALUES (%s,%s)",
                               (path.name, checksum))
            print(f"applied {path.name}")


if __name__ == "__main__":
    migrate()
