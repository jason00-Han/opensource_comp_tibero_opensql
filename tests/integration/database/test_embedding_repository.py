import pytest


pytestmark = [pytest.mark.integration, pytest.mark.openproxy]


def test_pgvector_embedding_upsert_contract(openproxy_connection):
    with openproxy_connection.cursor() as cursor:
        cursor.execute("select extversion from pg_extension where extname='vector'")
        assert cursor.fetchone() is not None, "pgvector extension is not installed"
        cursor.execute("create temporary table chunk_embeddings (chunk_id text, model text, embedding vector(3), primary key(chunk_id, model))")
        cursor.execute("insert into chunk_embeddings values (%s, %s, %s::vector)", ("chunk-1", "model", "[1,2,3]"))
        cursor.execute("insert into chunk_embeddings values (%s, %s, %s::vector) on conflict (chunk_id, model) do update set embedding=excluded.embedding", ("chunk-1", "model", "[3,2,1]"))
        cursor.execute("select embedding::text from chunk_embeddings")
        assert cursor.fetchone()[0] == "[3,2,1]"
    openproxy_connection.rollback()
