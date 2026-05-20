#!/usr/bin/env bash
# docker-manager entrypoint.
#
# The host's docker.sock is owned by gid=`docker`, which varies.
# We need our user to be in *that* group so socket access works
# without making the container privileged.

set -e

SOCK=/var/run/docker.sock
if [[ -S "$SOCK" ]]; then
  GID="$(stat -c '%g' "$SOCK")"
  if ! getent group "$GID" >/dev/null; then
    # add a group with that gid, no sudo (we're root in the build,
    # but at runtime we drop to `manager` — so we do this once at
    # image-build time? No: the gid is host-specific. We need to run
    # this as root and then drop. Trick: enter the container as root
    # via the entrypoint, then `exec gosu manager` — but we don't
    # want gosu. Simpler: run gunicorn as root *iff* needed only for
    # group setup, then chdir/setuid via Python's `os.setgid` /
    # `os.setuid` calls in app.py. We do this here.)
    addgroup --gid "$GID" dockerhost 2>/dev/null || groupadd -g "$GID" dockerhost
  fi
  usermod -aG "$GID" manager 2>/dev/null || true
fi

# Drop to the manager user and exec gunicorn-via-gevent
exec su -s /bin/bash manager -c \
  "gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
            -w 1 -b ${BARISTA_DM_BIND}:${BARISTA_DM_PORT} \
            --access-logfile - \
            'src.app:create_app()'"
