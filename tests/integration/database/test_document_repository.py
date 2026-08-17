import pytest


pytestmark = [pytest.mark.integration, pytest.mark.openproxy]


def test_document_and_chunks_transaction(openproxy_connection):
    with openproxy_connection.cursor() as cursor:
        cursor.execute("create temporary table documents (id text primary key, filename text not null)")
        cursor.execute("create temporary table chunks (document_id text, chunk_index integer, content text, primary key(document_id, chunk_index))")
        cursor.execute("insert into documents values (%s, %s)", ("doc-1", "guide.txt"))
        cursor.execute("insert into chunks values (%s, %s, %s)", ("doc-1", 0, "searchable"))
        cursor.execute("select d.filename, c.content from documents d join chunks c on c.document_id=d.id")
        assert cursor.fetchone() == ("guide.txt", "searchable")
    openproxy_connection.rollback()
