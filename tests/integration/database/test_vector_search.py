import pytest


pytestmark = [pytest.mark.integration, pytest.mark.openproxy]


def test_pgvector_orders_nearest_chunk(openproxy_connection):
    with openproxy_connection.cursor() as cursor:
        cursor.execute("select extversion from pg_extension where extname='vector'")
        assert cursor.fetchone() is not None, "pgvector extension is not installed"
        cursor.execute("create temporary table vectors (chunk_id text primary key, embedding vector(3))")
        cursor.execute("insert into vectors values ('near', '[1,0,0]'), ('far', '[0,1,0]')")
        cursor.execute("select chunk_id from vectors order by embedding <-> '[0.9,0.1,0]'::vector limit 1")
        assert cursor.fetchone() == ("near",)
    openproxy_connection.rollback()
