import os
import subprocess
from pathlib import Path

import psycopg
import pytest


pytestmark = [pytest.mark.integration, pytest.mark.openproxy, pytest.mark.failover]


def test_opensql_leader_failover_keeps_router_writable():
    script = Path("infra/scripts/failover-demo.ps1").resolve()
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS:" in result.stdout
    with psycopg.connect(os.environ["OPENPROXY_TEST_DSN"], connect_timeout=10) as connection:
        assert connection.execute("SELECT NOT pg_is_in_recovery()").fetchone()[0] is True
