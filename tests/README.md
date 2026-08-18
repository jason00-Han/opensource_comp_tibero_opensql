# Test suite

The suite is organized by system boundary instead of source directory.

- `unit/`: API validation, pipeline state machine/routing, worker processors, MCP service.
- `integration/embedding`: OpenAI-compatible HTTP request/response contract via `MockTransport`.
- `integration/mcp`: real MCP SDK client/server protocol calls.
- `integration/rabbitmq`: durable queue and persistent-message contract.
- `integration/openproxy`: PostgreSQL wire connection and transaction rollback through OpenProxy.
- `e2e/`: upload, RabbitMQ ingest, embedding, job status, and search lifecycle.
- `fixtures/`: stable document samples shared by parsers and lifecycle tests.

Fast tests require no external service:

```bash
make test
make test-unit
make test-integration
```

RabbitMQ tests require a running broker:

```bash
docker compose up -d rabbitmq
make test-rabbitmq
make test-e2e
```

OpenProxy tests are opt-in to avoid accidentally mutating a developer database. Use a dedicated
test database; the current contract test only creates a temporary table and rolls the transaction
back.

```bash
OPENPROXY_TEST_DSN='postgresql://postgres:pg_password@127.0.0.1:16432/opensql' \
  make test-openproxy
```

For the current `opensql-build-v2` container, host port `16432` maps to OpenProxy `6432` and
`opensql` is the configured pool name (the backend database is `postgres`). A successful client
handshake followed by `AllServersDown` means the proxy can be reached but cannot authenticate to
its configured backend.

Tests carrying `external_embedding` are reserved for a real configured model endpoint and should
not run in the default CI job.

## Windows one-command verification

The PowerShell runner never prints the DB password and loads it from the credential store created
by `tibero-doc setup`.

```powershell
# Unit tests, mocked boundaries, pipeline and MCP protocol
powershell -ExecutionPolicy Bypass -File .\scripts\test-service.ps1 fast

# Above plus the real OpenSQL/OpenProxy repositories and authenticated multi-user scenarios
powershell -ExecutionPolicy Bypass -File .\scripts\test-service.ps1 service

# Requires PRODUCTION_API_URLS, PRODUCTION_TLS_URL and MinIO S3_* variables
powershell -ExecutionPolicy Bypass -File .\scripts\test-service.ps1 production

# Destructive: asks for an explicit FAILOVER confirmation before stopping the HA leader
powershell -ExecutionPolicy Bypass -File .\scripts\test-service.ps1 failover
```

`service` verifies login, one-time refresh-token rotation, invitations, workspace isolation,
groups, ACL denial/grant, audit authorization, document versions, pgvector search, and MCP.
`production` verifies at least two directly addressable API instances, the Nginx HTTPS endpoint,
and a real encrypted MinIO object round trip. SMTP TLS/authentication is covered without sending
external mail by the unit test suite. RabbitMQ remains opt-in with `RUN_RABBITMQ_TESTS=1`.
