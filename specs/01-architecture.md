# 01 · Architecture

## The three planes

Barista splits responsibilities into three planes, all running on the
same host:

```
┌──────────────────────────── host machine ──────────────────────────────────┐
│                                                                            │
│  ┌─── CONTROL PLANE ───────────────────────────────────┐                   │
│  │  container: barista-bench-default                    │                   │
│  │  ┌────────────────────────────────────────────────┐ │                   │
│  │  │  Frappe bench                                   │ │   HTTP + token   │
│  │  │  apps: frappe, barista                          │ │  via barista-net │
│  │  │  site: barista.localhost  ← all Barista state   │─┼──────────┐       │
│  │  │  workers: default, long, barista-agent          │ │          │       │
│  │  │  NO /var/run/docker.sock                         │ │          │       │
│  │  └────────────────────────────────────────────────┘ │          │       │
│  └──────────────────────────────────────────────────────┘          │       │
│                                                                    │       │
│  ┌─── PRIVILEGE BOUNDARY (docker-manager) ──────────────────────────┘──┐   │
│  │  container: barista-docker-manager                                  │   │
│  │  Flask + Docker SDK, ~600 LOC, auditable in an afternoon            │   │
│  │  /var/run/docker.sock (rw)  ←  the ONLY thing with this             │   │
│  │  $BARISTA_HOME/data  (rw)   ←  bind-mount path resolution           │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                          │
│  ┌─── DATA PLANE ────────────── ▼ ──────────────────────────────────────┐  │
│  │   Docker daemon                                                       │  │
│  │     ├─ container: bench-default       (the control plane itself)      │  │
│  │     ├─ container: bench-myproject                                     │  │
│  │     ├─ container: bench-erpnext-v15                                   │  │
│  │     ├─ container: barista-mariadb     (shared DB server)              │  │
│  │     ├─ container: barista-redis       (shared cache/queue)            │  │
│  │     ├─ container: barista-traefik     (reverse proxy)                 │  │
│  │     └─ network:   barista-net         (user-defined bridge)           │  │
│  └─────────────────────────────────────────────────────────────────────────┘
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

**Control plane** = the Barista Frappe app. It is the *only* thing the
user logs into. It owns all DocTypes, the Vue dashboard, the REST/RT
API, and the queue jobs. **It does not have Docker access.**

**Privilege boundary** = the `docker-manager` Flask microservice. It is
the only process on the host that can talk to Docker. The control
plane reaches it via HTTP on `barista-net`. See
[09-docker-manager.md](09-docker-manager.md).

**Data plane** = the other bench containers and their sidecars
(MariaDB, Redis, Traefik). They have no awareness of Barista.

## Why is Barista itself in a container?

So that the install script has exactly one mode: "run Docker." If the
control plane were a native bench on the host, we'd have two install
paths (native install + Docker for others) and two upgrade stories.
With a single mode, `install.sh` is ~150 lines and the same on macOS,
Ubuntu, and a fresh VPS.

The control plane does **not** bind-mount `/var/run/docker.sock`.
Instead, a separate `barista-docker-manager` container holds the
socket and exposes a small HTTP API on the internal `barista-net`
network. This is the most important security decision in Barista —
the control plane runs user-installable Frappe code (apps,
customisations, server scripts) and we treat any such code as
untrusted. Moving Docker access out into a tiny separately-auditable
service keeps the blast radius small. See
[09-docker-manager.md](09-docker-manager.md) for the manager spec and
[08-security-and-permissions.md](08-security-and-permissions.md) for
the wider security model.

## Inspirations from frappe/press, and where we diverge

| Press concept | Barista equivalent | Notes |
|---|---|---|
| `Server` (a VM)            | `Bench Host` (a Docker container)    | Single host, so we drop `Cluster`, `Proxy Server`, `Database Server` as user-facing DocTypes — they become *services* inside a container. |
| `Release Group`            | `Bench Spec`                          | A versioned set of apps + Python/Node versions, used to build the bench image. |
| `Deploy` / `Deploy Candidate` | `Bench Build`                      | One row per image build. Status flows the same way (`Pending → Running → Success / Failure`). |
| `Site`                     | `Site`                                | Same idea: a Frappe site living on a Bench Host. |
| `Site Update`              | `Site Migration`                      | Triggered on app update or version bump. |
| `Agent` (HTTP daemon on each server) | `barista-docker-manager` (Flask) + agent queue | Press's agent is a Python HTTP service per server; Barista's manager is a single per-host service that the control-plane RQ workers call over HTTP. Same shape, scoped to one host. |
| `Site Backup`              | `Site Backup`                         | Same: rows in DB, files in a known location. |
| `Plan` / `Subscription`    | _not present_                         | Out of scope. |
| `Marketplace App`          | `Bench App` (source)                  | A row per "thing I might install": a Git URL + branch. |

## Processes inside the control-plane container

```
supervisord
├── frappe-web                    gunicorn, port 8000 inside the container
├── frappe-schedule               `bench schedule`
├── frappe-worker-default
├── frappe-worker-long
├── frappe-worker-barista-agent   talks HTTP to barista-docker-manager
├── frappe-socketio
├── nginx                         :80 (Traefik terminates TLS in front)
```

No process in this container has access to `/var/run/docker.sock`.
The `barista-agent` worker is the only one that talks to docker-manager,
because it is configured with `BARISTA_DOCKER_MANAGER_URL` and
`BARISTA_DOCKER_MANAGER_TOKEN` in its env; the other workers and the
web process don't have those vars set. This is enforced at the
supervisord level (env scoped per program) and audited via the
`Bench Action` DocType.

## How a user request flows

User clicks **"Restart bench"** in the UI:

```
1. Vue: $resources.restart.submit({ bench: 'myproject' })
        → POST /api/method/barista.api.bench.restart
2. Web worker: validates perms, inserts a `Bench Action` doc
        status="Queued", action="Restart"
3. Web worker: frappe.enqueue(
        method="barista.tasks.bench.restart",
        queue="barista-agent",
        bench_action=<name>,
   )
4. barista-agent worker:
   - publish_realtime("bench:myproject:status", "restarting")
   - POST http://barista-docker-manager:8080/v1/benches/myproject/restart
        with `X-Auth-Token: <BARISTA_DOCKER_MANAGER_TOKEN>`
   - publish_realtime("bench:myproject:status", "running")
   - update Bench Action: status="Success", duration=...
5. Vue: realtime subscription updates the row's status badge live.
```

Every privileged action goes through the same five-step shape:
DocType row → enqueue → worker uses Docker SDK → realtime event →
audit row. There is no other path. This makes the system easy to
reason about and to audit.

## Storage layout on the host

```
~/.barista/
├── docker-compose.yml          # written by install.sh
├── .env                        # passwords, ports
├── data/
│   ├── mariadb/                # bind mount, one DB server for all benches
│   ├── redis/
│   └── benches/
│       ├── default/            # ← this one is the control-plane bench
│       │   ├── apps/
│       │   ├── sites/
│       │   └── logs/
│       ├── myproject/
│       └── erpnext-v15/
└── backups/
    └── <site>/<timestamp>.tar.gz
```

One MariaDB instance hosts every site's database — same pattern as
`frappe-bench` defaults. Each bench container mounts its own
`benches/<name>/` directory as its working dir, so apps and logs are
visible to the host (and survive container destruction).
