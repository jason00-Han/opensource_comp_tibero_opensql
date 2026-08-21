from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg


def database_dsn() -> str | None:
    """Return the configured OpenSQL DSN.

    The OpenProxy DSN normally looks like
    ``postgresql://postgres:password@127.0.0.1:16432/opensql``.
    """

    return os.getenv("TIBERO_DOC_DSN") or os.getenv("DATABASE_URL")


@contextmanager
def connect(dsn: str | None = None) -> Iterator[psycopg.Connection]:
    configured = dsn or database_dsn()
    if not configured:
        raise RuntimeError("TIBERO_DOC_DSN is not configured")
    with psycopg.connect(configured, connect_timeout=5) as connection:
        yield connection


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.12g}" for value in vector) + "]"


def check_database(dsn: str | None = None) -> dict[str, object]:
    with connect(dsn) as connection:
        row = connection.execute(
            "SELECT current_database(), pg_is_in_recovery(), current_user"
        ).fetchone()
    return {
        "database": row[0],
        "is_replica": row[1],
        "user": row[2],
    }
