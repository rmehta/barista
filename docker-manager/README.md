# Barista Docker Manager

A tiny privileged microservice that owns `/var/run/docker.sock` so
that the Barista Frappe app doesn't have to. Barista calls this
service over HTTP across the `barista-net` Docker network.

See [../09-docker-manager.md](../09-docker-manager.md) for the spec.

## Run

Standalone (for local dev):

```bash
export BARISTA_DOCKER_MANAGER_TOKEN=devtoken
export BARISTA_DATA_ROOT=$HOME/.barista/data
export BARISTA_TRAEFIK_DYNAMIC=$HOME/.barista/config/traefik/dynamic.yml
pip install -r requirements.txt
gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
         -w 1 -b 127.0.0.1:8080 'src.app:create_app()'
```

In production (via Barista's `docker-compose.yml`):

```yaml
docker-manager:
  container_name: barista-docker-manager
  build: ./docker-manager
  restart: unless-stopped
  networks: [barista-net]
  environment:
    BARISTA_DOCKER_MANAGER_TOKEN: ${BARISTA_DOCKER_MANAGER_TOKEN}
    BARISTA_DATA_ROOT: /data
    BARISTA_TRAEFIK_DYNAMIC: /etc/traefik/dynamic.yml
    NETWORK: ${BARISTA_DOCKER_NETWORK}
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
    - ${HOME}/.barista/data:/data
    - ${HOME}/.barista/config/traefik:/etc/traefik
  # NO `ports:` — internal network only
```

## Test

```bash
curl -H "X-Auth-Token: devtoken" http://localhost:8080/v1/health
```

## Layout

```
src/
├── app.py        Flask factory; loads blueprints
├── auth.py       Token + CIDR allowlist (before_request hook)
├── policy.py     Container-creation validation; the chokepoint
├── manager.py    Bench lifecycle (create / start / stop / etc.)
├── builds.py     Image builds + pulls (long tasks)
├── exec_ops.py   One-shot exec + websocket terminal
├── routes.py     Traefik dynamic.yml writer
└── tasks.py      In-memory task table + threadpool
```
