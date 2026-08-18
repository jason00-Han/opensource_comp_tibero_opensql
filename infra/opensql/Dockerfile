ARG OPENSQL_BASE_IMAGE=opensql-systemd-ready:latest
FROM ${OPENSQL_BASE_IMAGE}

USER root

COPY --chown=opensql:opensql patroni.yml /opt/tibero-doc/templates/patroni.yml
COPY --chown=opensql:opensql openproxy.toml /opt/tibero-doc/templates/openproxy.toml
COPY --chown=opensql:opensql init.sql /opt/tibero-doc/init.sql
COPY --chown=opensql:opensql entrypoint.sh /usr/local/bin/tibero-doc-opensql-entrypoint

RUN chmod 0755 /usr/local/bin/tibero-doc-opensql-entrypoint \
    && mkdir -p /home/opensql/data/pgsql /home/opensql/etc/etcd/etcd_data /home/opensql/logs \
    && chown -R opensql:opensql /home/opensql/data /home/opensql/etc /home/opensql/logs

USER opensql
WORKDIR /home/opensql

EXPOSE 2379 2380 5432 6432 8008

ENTRYPOINT ["/usr/local/bin/tibero-doc-opensql-entrypoint"]
