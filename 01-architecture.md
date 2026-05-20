# 01 · Architecture

## The two planes

Barista uses the classic **control plane / data plane** split, except
both planes live on the same host.

```
┌──────────────────────────── host machine ─────────────────────────────┐
│                                                                       │
│   ┌─── CONTROL PLANE ───────────────────────────────────────────┐     │
│   │                                                             │     │
│   │   Docker container: barista-bench-01                        │     │
│   │   ┌────────────────────────────────────────────────────┐   │     │
│   │   │  Frappe bench                                       │   │     │
│   │   │  apps: frappe, barista                              │   │     │
│   │   │  site: barista.localhost  ← stores ALL Barista state│   │     │
│   │   │                                                     │   │     │
│   │   │  workers (rq):                                      │   │     │
│   │   │    - default        (UI requests)                   │   │     │
│   │   │    - long           (build images, restore backups) │   │     │
│   │   │    - barista-agent  (docker calls, log tailers)     │   │     │
│   │   └────────────────────────────────────────────────────┘   │     │
│   │                          │                                  │     │
│   │             /var/run/docker.sock (bind mount)              │     │
│   │                          ▼                                  │     │
│   └─────────────────────────┼──────────────────────────────────┘     │
│                             │                                         │
│   ┌─── DATA PLANE ──────────┼──────────────────────────────────┐     │
│   │                         ▼                                   │     │
│   │   Docker daemon                                             │     │
│   │     ├─ container: bench-default      (the one above)        │     │
│   │     ├─ container: bench-myproject                           │     │
│   │     ├─ container: bench-erpnext-v15                         │     │
│   │     ├─ container: barista-mariadb    (shared DB server)     │     │
│   │     ├─ container: barista-redis      (shared cache/queue)   │     │
│   │     └─ network:   barista-net       (user-defined bridge)   │     │
│   └────────────────────────────────────────────────────────────┘     │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

**Control plane** = the Barista Frappe app. It is the *only* thing the
user logs into. It owns all DocTypes, the Vue dashboard, the REST/RT
API, and the queue jobs that talk to Docker.

**Data plane** = the other bench containers and their sidecars
(MariaDB, Redis). They have no awareness of Barista.

## Why is Barista itself in a container?

So that the install script has exactly one mode: "run Docker." If the
control plane were a native bench on the host, we'd have two install
paths (native install + Docker for others) and two upgrade stories.
With a single mode, `install.sh` is ~50 lines and the same on macOS,
Ubuntu, and a fresh VPS.

The tradeoff: the control-plane container must bind-mount
`/var/run/docker.sock` so its workers can launch sibling containers.
That's a privilege escalation in disguise (anyone who can write to
that socket is effectively root on the host) — so the container runs
**rootless Docker** on Linux where possible, and the socket is only
exposed to the worker process, not the web process. See
[08-security-and-permissions.md](08-security-and-permissions.md).

## Inspirations from frappe/press, and where we diverge

| Press concept | Barista equivalent | Notes |
|---|---|---|
| `Server` (a VM)            | `Bench Host` (a Docker container)    | Single host, so we drop `Cluster`, `Proxy Server`, `Database Server` as user-facing DocTypes — they become *services* inside a container. |
| `Release Group`            | `Bench Spec`                          | A versioned set of apps + Python/Node versions, used to build the bench image. |
| `Deploy` / `Deploy Candidate` | `Bench Build`                      | One row per image build. Status flows the same way (`Pending → Running → Success / Failure`). |
| `Site`                     | `Site`                                | Same idea: a Frappe site living on a Bench Host. |
| `Site Update`              | `Site Migration`                      | Triggered on app update or version bump. |
| `Agent` (HTTP daemon on each server) | `Barista Agent` (worker queue) | Press's agent is a separate Python HTTP service; Barista does the same work as RQ jobs in the control-plane bench, since `docker.sock` is reachable directly. **Big simplification.** |
| `Site Backup`              | `Site Backup`                         | Same: rows in DB, files in a known location. |
| `Plan` / `Subscription`    | _not present_                         | Out of scope. |
| `Marketplace App`          | `Bench App` (source)                  | A row per "thing I might install": a Git URL + branch. |

## Processes inside the control-plane container

```
supervisord
├── frappe-web         gunicorn, port 8000 inside the container
├── frappe-schedule    `bench schedule`
├── frappe-worker-default
├── frappe-worker-long
├── frappe-worker-barista-agent     ← only this one has DOCKER_HOST set
├── frappe-socketio
├── nginx              :80 / :443 (terminates TLS for *.localhost / your domain)
└── redis-cache, redis-queue   (or external via env)
```

The `barista-agent` worker is the only process with Docker access.
Everything else hits Docker indirectly by enqueueing jobs onto that
worker's queue. This is enforced at the worker definition level (see
[02-doctypes.md](02-doctypes.md) → `Barista Settings`) and audited via
the `Bench Action` DocType.

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
   - docker.containers.get('bench-myproject').restart()
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
