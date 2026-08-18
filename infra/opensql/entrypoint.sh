#!/usr/bin/env bash
set -Eeuo pipefail

OPENSQL_HOME="${OPENSQL_HOME:-/home/opensql}"
POSTGRES_PASSWORD="${OPENSQL_POSTGRES_PASSWORD:?OPENSQL_POSTGRES_PASSWORD is required}"
REPLICATION_PASSWORD="${OPENSQL_REPLICATION_PASSWORD:?OPENSQL_REPLICATION_PASSWORD is required}"
REWIND_PASSWORD="${OPENSQL_REWIND_PASSWORD:?OPENSQL_REWIND_PASSWORD is required}"
LICENSE_SOURCE="${OPENSQL_LICENSE_SOURCE:-/run/secrets/opensql-license.xml}"
NODE_NAME="${OPENSQL_NODE_NAME:-postgresql1}"
NODE_ADDRESS="${OPENSQL_NODE_ADDRESS:-127.0.0.1}"
ETCD_HOSTS="${OPENSQL_ETCD_HOSTS:-127.0.0.1:2379}"

for value in "$POSTGRES_PASSWORD" "$REPLICATION_PASSWORD" "$REWIND_PASSWORD"; do
    if [[ "$value" == *'"'* || "$value" == *'\'* || "$value" == *$'\n'* ]]; then
        echo "Passwords must not contain quotes, backslashes, or newlines." >&2
        exit 64
    fi
done

if [[ ! -f "$LICENSE_SOURCE" ]]; then
    echo "OpenSQL license not found at $LICENSE_SOURCE" >&2
    echo "Set OPENSQL_LICENSE_FILE to the host path of your licensed file." >&2
    exit 66
fi

mkdir -p \
    "$OPENSQL_HOME/data/pgsql" \
    "$OPENSQL_HOME/etc/etcd/etcd_data" \
    "$OPENSQL_HOME/etc/patroni" \
    "$OPENSQL_HOME/etc/openproxy" \
    "$OPENSQL_HOME/license" \
    "$OPENSQL_HOME/logs" \
    "$OPENSQL_HOME/tmp"
cp "$LICENSE_SOURCE" "$OPENSQL_HOME/license/license.xml"

sed \
    -e "s|{{POSTGRES_PASSWORD}}|$POSTGRES_PASSWORD|g" \
    -e "s|{{REPLICATION_PASSWORD}}|$REPLICATION_PASSWORD|g" \
    -e "s|{{REWIND_PASSWORD}}|$REWIND_PASSWORD|g" \
    -e "s|{{NODE_NAME}}|$NODE_NAME|g" \
    -e "s|{{NODE_ADDRESS}}|$NODE_ADDRESS|g" \
    -e "s|{{ETCD_HOSTS}}|$ETCD_HOSTS|g" \
    /opt/tibero-doc/templates/patroni.yml > "$OPENSQL_HOME/etc/patroni/patroni.yml"
sed \
    -e "s|{{POSTGRES_PASSWORD}}|$POSTGRES_PASSWORD|g" \
    /opt/tibero-doc/templates/openproxy.toml > "$OPENSQL_HOME/etc/openproxy/openproxy.toml"

export OPENSQL_HOME
export OPENSQL_LICENSE_PATH="$OPENSQL_HOME/license/license.xml"
export PATH="$OPENSQL_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$OPENSQL_HOME/lib:${LD_LIBRARY_PATH:-}"

terminate() {
    trap - TERM INT
    kill -TERM "${OPENPROXY_PID:-}" "${PATRONI_PID:-}" "${ETCD_PID:-}" 2>/dev/null || true
    wait || true
}
trap terminate TERM INT

if [[ "${OPENSQL_EXTERNAL_ETCD:-false}" != "true" ]]; then
"$OPENSQL_HOME/bin/etcd" \
    --name etcd1 \
    --data-dir "$OPENSQL_HOME/etc/etcd/etcd_data" \
    --listen-client-urls http://0.0.0.0:2379 \
    --advertise-client-urls http://127.0.0.1:2379 \
    --listen-peer-urls http://0.0.0.0:2380 \
    --initial-advertise-peer-urls http://127.0.0.1:2380 \
    --initial-cluster etcd1=http://127.0.0.1:2380 \
    --initial-cluster-token opensql-etcd-cluster \
    --initial-cluster-state new \
    >> "$OPENSQL_HOME/logs/etcd.log" 2>&1 &
ETCD_PID=$!
fi

ETCD_HEALTH_HOST="${ETCD_HOSTS%%,*}"; ETCD_HEALTH_HOST="${ETCD_HEALTH_HOST/:2379/}"
for _ in {1..30}; do
    curl -fsS "http://${ETCD_HEALTH_HOST}:2379/health" >/dev/null 2>&1 && break
    sleep 1
done
curl -fsS "http://${ETCD_HEALTH_HOST}:2379/health" >/dev/null

"$OPENSQL_HOME/bin/patroni" "$OPENSQL_HOME/etc/patroni/patroni.yml" \
    >> "$OPENSQL_HOME/logs/patroni.log" 2>&1 &
PATRONI_PID=$!

for _ in {1..90}; do
    curl -fsS http://127.0.0.1:8008/health >/dev/null 2>&1 && break
    kill -0 "$PATRONI_PID" 2>/dev/null || { tail -n 100 "$OPENSQL_HOME/logs/patroni.log"; exit 1; }
    sleep 1
done
curl -fsS http://127.0.0.1:8008/health >/dev/null

if curl -fsS http://127.0.0.1:8008/primary >/dev/null 2>&1; then
PGPASSWORD="$POSTGRES_PASSWORD" "$OPENSQL_HOME/bin/psql" \
    -h 127.0.0.1 -p 5432 -U postgres -d postgres \
    -v ON_ERROR_STOP=1 -f /opt/tibero-doc/init.sql
fi

if [[ "${OPENSQL_OPENPROXY_ENABLED:-true}" == "true" ]]; then
"$OPENSQL_HOME/bin/openproxy" "$OPENSQL_HOME/etc/openproxy/openproxy.toml" \
    >> "$OPENSQL_HOME/logs/openproxy.log" 2>&1 &
OPENPROXY_PID=$!
fi

wait -n "$PATRONI_PID" ${ETCD_PID:+"$ETCD_PID"} ${OPENPROXY_PID:+"$OPENPROXY_PID"}
status=$?
echo "An OpenSQL component exited with status $status" >&2
terminate
exit "$status"
