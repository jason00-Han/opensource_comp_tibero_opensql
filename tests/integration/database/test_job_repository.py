import pytest


pytestmark = [pytest.mark.integration, pytest.mark.openproxy]


def test_job_status_upsert_contract(openproxy_connection):
    with openproxy_connection.cursor() as cursor:
        cursor.execute("create temporary table pipeline_jobs (job_id text primary key, status text not null, result jsonb)")
        cursor.execute("insert into pipeline_jobs values (%s, %s, null)", ("job-1", "queued"))
        cursor.execute("update pipeline_jobs set status=%s, result=%s::jsonb where job_id=%s", ("completed", '{"chunks":1}', "job-1"))
        cursor.execute("select status, result->>'chunks' from pipeline_jobs where job_id=%s", ("job-1",))
        assert cursor.fetchone() == ("completed", "1")
    openproxy_connection.rollback()
