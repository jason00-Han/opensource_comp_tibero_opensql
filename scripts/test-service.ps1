param(
    [ValidateSet('fast', 'service', 'production', 'failover')]
    [string]$Suite = 'service'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    throw "가상환경을 찾을 수 없습니다: $Python"
}
Set-Location -LiteralPath $Root
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = 'cli/src;.'

if ($Suite -eq 'fast') {
    & $Python -m pytest -m 'not rabbitmq and not openproxy and not minio and not production and not failover' -q -ra
    exit $LASTEXITCODE
}

if ($Suite -eq 'service') {
    & $Python -m pytest -m 'not rabbitmq and not openproxy and not minio and not production and not failover' -q -ra
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $env:RUN_MCP_HTTP_TESTS = '1'
    & $Python -m pytest tests/integration/mcp/test_streamable_http.py -q -ra
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    @'
import os, pytest
from tibero_doc.config import load_config, load_password, build_dsn
c = load_config()
p = load_password(c)
if not p:
    raise SystemExit("저장된 DB 비밀번호가 없습니다. tibero-doc setup을 먼저 실행하세요.")
dsn = build_dsn(p, c)
os.environ["OPENPROXY_TEST_DSN"] = dsn
os.environ["TIBERO_DOC_DSN"] = dsn
raise SystemExit(pytest.main(["tests/integration/database", "-q", "-ra", "-m", "not failover"]))
'@ | & $Python -
    exit $LASTEXITCODE
}

if ($Suite -eq 'production') {
    $env:RUN_PRODUCTION_TESTS = '1'
    $env:RUN_MINIO_TESTS = '1'
    & $Python -m pytest tests/integration/deployment tests/integration/storage -q -ra
    exit $LASTEXITCODE
}

if ($Suite -eq 'failover') {
    $answer = Read-Host '현재 OpenSQL HA Primary를 의도적으로 중지합니다. 계속하려면 FAILOVER 입력'
    if ($answer -cne 'FAILOVER') { throw 'Failover 테스트를 취소했습니다.' }
    $env:RUN_FAILOVER_TESTS = '1'
    @'
import os, pytest
from tibero_doc.config import load_config, load_password, build_dsn
c = load_config(); p = load_password(c)
if not p: raise SystemExit("저장된 DB 비밀번호가 없습니다.")
dsn = build_dsn(p, c)
os.environ["OPENPROXY_TEST_DSN"] = dsn
os.environ["TIBERO_DOC_DSN"] = dsn
raise SystemExit(pytest.main(["tests/integration/database/test_failover.py", "-q", "-ra"]))
'@ | & $Python -
    exit $LASTEXITCODE
}
