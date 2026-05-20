FROM python:3.12-slim

# docker-manager runs gunicorn as the non-root `manager` user, but
# the *entrypoint* must run as root so it can add `manager` to a
# group matching the host docker socket's GID (which varies per
# host). entrypoint.sh does the privilege drop via `su` once that's
# done. So: NO `USER manager` in this Dockerfile.

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1001 -s /bin/bash manager

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    BARISTA_DM_BIND=0.0.0.0 \
    BARISTA_DM_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -fsS -H "X-Auth-Token: $BARISTA_DOCKER_MANAGER_TOKEN" \
      http://localhost:8080/v1/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
