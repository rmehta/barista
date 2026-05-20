# 06 · Install & Bootstrap

## Goal

Two friendly entry points, each idempotent:

1. `curl -fsSL https://raw.githubusercontent.com/frappe/barista/main/install.sh | bash`
   on a fresh laptop or VPS — see [install.sh](install.sh).
2. From an existing bench: `bench get-app barista && bench --site … install-app barista`
   for power users.

Both arrive at the same end state: one running `barista-bench-default`
container with the `barista.localhost` site initialised.

## What `install.sh` does

In order — but every step is **a function** with a "skip if already
done" guard, so re-running is safe.

```
1.  preflight()             — OS check, Docker presence, ports free, disk space
2.  ensure_docker()         — install if missing, start daemon
3.  ensure_dirs()           — ~/.barista/{data,config,backups,src}, ownership
4.  write_env()             — generate ~/.barista/.env (passwords, tokens, ports), once
5.  write_mariadb_conf()    — slow-log enabled my.cnf
6.  write_traefik_conf()    — static + empty dynamic config
7.  stage_docker_manager()  — copy docker-manager/ source to ~/.barista/src
                              (or clone from BARISTA_REPO if running curl|bash)
8.  write_compose()         — render ~/.barista/docker-compose.yml from template
9.  compose_up()            — build docker-manager image, pull mariadb/redis/traefik,
                              `up -d`, wait for MariaDB and docker-manager health
10. bootstrap_cp()          — create the control-plane bench container (NO docker.sock!),
                              create barista.localhost site, install barista app,
                              register-control-plane (writes Bench Host & Site rows)
11. print_summary()         — print URL + admin password; on macOS, `open`.
```

### Preflight

```bash
preflight() {
  case "$(uname -s)" in
    Darwin|Linux) ;;
    *) die "Unsupported OS";;
  esac

  command -v docker >/dev/null || NEEDS_DOCKER=1
  port_free 80 || warn "port 80 in use; traefik will fail until free"
  port_free 443 || warn "port 443 in use"
  free_gb=$(df -h ~ | awk 'NR==2 {print $4}' | tr -d 'Gi')
  [[ ${free_gb%.*} -ge 5 ]] || die "Need at least 5 GB free in \$HOME"
}
```

### `~/.barista/.env`

Generated **once**, then never overwritten. Contains:

```
BARISTA_VERSION=0.1.0
BARISTA_MARIADB_ROOT_PASSWORD=<32-byte hex>
BARISTA_ADMIN_PASSWORD=<24-byte hex>        # initial Barista admin
BARISTA_DOCKER_MANAGER_TOKEN=<32-byte hex>  # auth between control plane and manager
BARISTA_TIMEZONE=Asia/Kolkata
BARISTA_HTTP_PORT_RANGE_START=18000
BARISTA_DOMAIN=barista.localhost            # override for VPS installs
BARISTA_LETSENCRYPT_EMAIL=                  # only used when domain != *.localhost
BARISTA_DOCKER_NETWORK=barista-net
```

The user gets a chance to edit before step 5 if `--interactive` is
passed; otherwise reasonable defaults.

### `docker-compose.yml` template

```yaml
name: barista
networks:
  barista-net:
    name: ${BARISTA_DOCKER_NETWORK}

volumes:
  mariadb-data:
    driver_opts: { type: none, o: bind, device: ${HOME}/.barista/data/mariadb }
  redis-data:
    driver_opts: { type: none, o: bind, device: ${HOME}/.barista/data/redis }

services:
  mariadb:
    container_name: barista-mariadb
    image: mariadb:11
    restart: unless-stopped
    networks: [barista-net]
    environment:
      MARIADB_ROOT_PASSWORD: ${BARISTA_MARIADB_ROOT_PASSWORD}
    volumes:
      - mariadb-data:/var/lib/mysql
      - ${HOME}/.barista/config/mariadb/my.cnf:/etc/mysql/conf.d/my.cnf:ro
      - ${HOME}/.barista/data/mariadb-logs:/var/log/mysql
    ports:
      - "127.0.0.1:13306:3306"

  redis:
    container_name: barista-redis
    image: redis:7-alpine
    restart: unless-stopped
    networks: [barista-net]
    volumes:
      - redis-data:/data

  traefik:
    container_name: barista-traefik
    image: traefik:v3.1
    restart: unless-stopped
    networks: [barista-net]
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ${HOME}/.barista/config/traefik:/etc/traefik:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ${HOME}/.barista/data/traefik:/data

  docker-manager:
    container_name: barista-docker-manager
    build:
      context: ${HOME}/.barista/src/docker-manager
    restart: unless-stopped
    networks: [barista-net]
    # NO `ports:` — internal Docker network only
    environment:
      BARISTA_DOCKER_MANAGER_TOKEN: ${BARISTA_DOCKER_MANAGER_TOKEN}
      NETWORK: ${BARISTA_DOCKER_NETWORK}
      BARISTA_DATA_ROOT: /data
      BARISTA_TRAEFIK_DYNAMIC: /etc/traefik/dynamic.yml
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ${HOME}/.barista/data:/data
      - ${HOME}/.barista/config/traefik:/etc/traefik
    labels:
      barista.role: docker-manager
```

### Bootstrapping the control-plane bench

This is the only step that's a little magic — it has to create the
"first bench" without Barista being available yet to do it for us. So
`install.sh` uses `docker run` and `bench` directly, *once*:

```bash
bootstrap_cp() {
  test -d "$HOME/.barista/data/benches/default/sites" && return 0

  log "Initialising control-plane bench (one-time)…"

  mkdir -p "$HOME/.barista/data/benches/default"
  chown -R 1000:1000 "$HOME/.barista/data/benches/default"

  # one-time helper container to run `bench init`
  docker run --rm \
    -v "$HOME/.barista/data/benches/default:/home/frappe/bench-init" \
    --network ${BARISTA_DOCKER_NETWORK} \
    ghcr.io/frappe/bench-base:python3.11-node20 \
    bash -c '
      cd /home/frappe &&
      bench init --skip-redis-config-generation \
                 --frappe-branch version-15 \
                 bench-tmp &&
      mv bench-tmp/* bench-init/ &&
      mv bench-tmp/.??* bench-init/
    '

  # write common_site_config.json pointing at the shared services
  cat > "$HOME/.barista/data/benches/default/sites/common_site_config.json" <<JSON
{
  "db_host": "barista-mariadb",
  "db_port": 3306,
  "redis_cache":   "redis://barista-redis:6379/0",
  "redis_queue":   "redis://barista-redis:6379/1",
  "redis_socketio":"redis://barista-redis:6379/2"
}
JSON

  # the long-lived bench container — note: NO docker.sock mount
  docker run -d --name barista-bench-default \
    --network ${BARISTA_DOCKER_NETWORK} \
    -v "$HOME/.barista/data/benches/default:/home/frappe/bench" \
    -v "$HOME/.barista/backups:/backups" \
    -p "127.0.0.1:18000:80" \
    -e BARISTA_DOCKER_MANAGER_URL=http://barista-docker-manager:8080 \
    -e BARISTA_DOCKER_MANAGER_TOKEN=${BARISTA_DOCKER_MANAGER_TOKEN} \
    --label "barista.role=control-plane" \
    --label "traefik.enable=true" \
    --label "traefik.http.routers.barista.rule=Host(\`${BARISTA_DOMAIN}\`)" \
    --label "traefik.http.services.barista.loadbalancer.server.port=80" \
    ghcr.io/frappe/bench-base:python3.11-node20 \
    /entrypoint.sh

  # install barista the app
  docker exec -u frappe barista-bench-default bash -lc "
    cd /home/frappe/bench &&
    bench get-app --branch main https://github.com/frappe/barista &&
    bench new-site --no-mariadb-socket \
                   --admin-password '${BARISTA_ADMIN_PASSWORD}' \
                   --mariadb-root-password '${BARISTA_MARIADB_ROOT_PASSWORD}' \
                   --install-app barista \
                   ${BARISTA_DOMAIN}
  "

  # now hand-write the corresponding rows into the Barista site so it
  # knows about itself
  docker exec -u frappe barista-bench-default bash -lc "
    cd /home/frappe/bench &&
    bench --site ${BARISTA_DOMAIN} execute \
      barista.install.register_control_plane
  "
}
```

The `barista.install.register_control_plane` function inserts:

- a `Bench Spec` named `barista-cp`, marked `is_system = 1`
- a `Bench Build` row referencing the bench-base image directly (so
  build history shows this even though `install.sh` did the work)
- a `Bench Host` named `default`, status `Running`, with the right
  `container_id`, `host_path`, `http_port`
- a `Site` row for `barista.localhost` with `is_control_plane = 1`,
  installed apps `frappe` and `barista`, `bench = default`.

This means the **very first thing a user sees on the dashboard** is
their own bench/site already listed and healthy — not an empty state.

### Flags `install.sh` accepts

```
--domain <hostname>    use a real domain (turns on Let's Encrypt)
--email  <addr>        Let's Encrypt contact email
--port-start <n>       start of HTTP port range; default 18000
--no-traefik           skip traefik; you'll proxy in your own nginx/caddy
--interactive          prompt before writing .env
--dry-run              print what would happen, do nothing
--uninstall            stop containers, delete networks, leave data alone
--purge                ⚠ delete EVERYTHING under ~/.barista
```

`--uninstall` is the "I'm done playing" button; `--purge` requires a
typed confirmation. Neither deletes Docker images by default (they're
big and re-downloadable; user can `docker image prune` themselves).

## First-run wizard (in the UI)

When the user opens `https://barista.localhost/barista` for the first
time, they hit a wizard backed by a small DocType
`Onboarding Status (Single)`:

```
┌─ Welcome to Barista ☕ ────────────────────────────────────────────────────┐
│                                                                            │
│  Step 1 — Sign in as your admin                                            │
│    email:    rmehta@…                                                      │
│    full name: Rushabh                                                      │
│    password: ●●●●●●●●●●                                                    │
│                                                                            │
│  Step 2 — Tell us about this host (optional)                               │
│    [x] Enable web analytics on new sites                                   │
│    [ ] Enable MariaDB binary logs (uses more disk)                         │
│                                                                            │
│  Step 3 — All set!                                                         │
│    You can now create more benches, add app sources, or just play          │
│    around in the existing default bench.                                   │
│                                                                            │
│                                                              [Get started] │
└────────────────────────────────────────────────────────────────────────────┘
```

The wizard never blocks — every step is skippable. Onboarding state is
on the single DocType so power-users can flip `completed = 1` from the
console without seeing the modal.

## Idempotency contract

- Running `install.sh` again on a healthy machine prints "already
  installed, nothing to do" and exits 0.
- Running it after a failed install resumes at the first incomplete
  step. Each step writes a marker file in `~/.barista/.state/` on
  success.
- `bench --site barista.localhost migrate` works the standard way for
  Barista app upgrades; no special command needed.

## Upgrading

```
barista upgrade            # convenience wrapper, also lives in install.sh
# = pull new bench-base, rebuild control-plane image, migrate site
```

The control-plane bench is rebuilt the same way any other bench is —
via a `Bench Build` — so the upgrade path is exercised by everyday
use. No separate code path for "upgrading Barista itself."

## What if Docker isn't available?

`install.sh` will offer to install it (with explicit confirmation) on
Linux via the official `get.docker.com` script. On macOS it points
the user at the Docker Desktop installer URL (we don't auto-install
Desktop because licensing). If the user declines, the script exits
with a clear message and a `--no-docker-install` flag they can pass
to suppress the prompt next time.
