# Reproducible single-node OpenSQL development environment

This directory contains project-owned configuration only. It does not redistribute OpenSQL,
OpenProxy, or a license. Obtain an official OpenSQL container image and license under their
applicable terms, then tag the image locally (the default expected tag is
`opensql-systemd-ready:latest`).

1. Copy `infra/opensql/.env.example` to `infra/opensql/.env`.
2. Put your licensed file at the path configured by `OPENSQL_LICENSE_FILE`.
3. Use strong local passwords without quotes, backslashes, or newlines.
4. Start the environment from the repository root:

```bash
docker compose --env-file infra/opensql/.env -f infra/docker-compose.opensql.yml up -d --build
docker compose --env-file infra/opensql/.env -f infra/docker-compose.opensql.yml ps
```

The host DSN uses the OpenProxy pool name `opensql` as its database segment:

```text
postgresql://postgres:<URL-ENCODED-PASSWORD>@127.0.0.1:16432/opensql
```

The entrypoint starts a single etcd member, bootstraps a single Patroni primary, enables pgvector,
applies `init.sql`, and starts OpenProxy. This is a portable development topology, not HA. Real HA
requires at least three DCS members and two or more PostgreSQL/Patroni nodes with distinct reachable
addresses.

To reset all database state (destructive):

```bash
docker compose --env-file infra/opensql/.env -f infra/docker-compose.opensql.yml down -v
```
