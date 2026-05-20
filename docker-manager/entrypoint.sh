#!/usr/bin/env bash
# docker-manager entrypoint.
#
# Runs as ROOT so it can:
#   1. Create a group inside the container matching the host docker
#      socket's GID (this varies per host — Linux rootful: the
#      `docker` group GID; Linux rootless: usually 0; Docker Desktop:
#      0). Without root we can't `groupadd`.
#   2. Add the `manager` user to that group.
#   3. Drop privileges via `su` before exec'ing gunicorn.
#
# After that gunicorn (and therefore Flask and the Docker SDK) runs
# as uid 1001 (`manager`).

set -e

SOCK=/var/run/docker.sock
if [[ -S "$SOCK" ]]; then
  GID="$(stat -c '%g' "$SOCK")"
  if ! getent group "$GID" >/dev/null; then
    groupadd -g "$GID" dockerhost
  fi
  usermod -aG "$GID" manager
fi

exec su -s /bin/bash manager -c \
  "gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
            -w 1 -b ${BARISTA_DM_BIND}:${BARISTA_DM_PORT} \
            --access-logfile - \
            'src.app:create_app()'"
