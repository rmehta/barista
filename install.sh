#!/usr/bin/env bash
#
# Barista installer
# -----------------
# Sets up Barista on a fresh host: Docker, shared services (MariaDB,
# Redis, Traefik), and the first bench + barista.localhost site.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/frappe/barista/main/install.sh | bash
#   ./install.sh [--domain HOST] [--email ADDR] [--port-start N]
#                [--interactive] [--dry-run]
#                [--uninstall | --purge]
#
# Idempotent: re-running is safe. Each step writes a marker under
# ~/.barista/.state/ on success; subsequent runs skip done steps.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults & flags
# ---------------------------------------------------------------------------

BARISTA_HOME="${BARISTA_HOME:-$HOME/.barista}"
BARISTA_REPO="${BARISTA_REPO:-https://github.com/frappe/barista}"
BARISTA_BRANCH="${BARISTA_BRANCH:-main}"
BASE_IMAGE="${BASE_IMAGE:-ghcr.io/frappe/bench-base:python3.11-node20}"
NETWORK="${NETWORK:-barista-net}"

DOMAIN="barista.localhost"
EMAIL=""
PORT_START=18000
INTERACTIVE=0
DRY_RUN=0
NO_TRAEFIK=0
MODE="install"   # install | uninstall | purge

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)       DOMAIN="$2"; shift 2 ;;
    --email)        EMAIL="$2"; shift 2 ;;
    --port-start)   PORT_START="$2"; shift 2 ;;
    --no-traefik)   NO_TRAEFIK=1; shift ;;
    --interactive)  INTERACTIVE=1; shift ;;
    --dry-run)      DRY_RUN=1; shift ;;
    --uninstall)    MODE="uninstall"; shift ;;
    --purge)        MODE="purge"; shift ;;
    -h|--help)
      sed -n '2,20p' "$0"; exit 0 ;;
    *)
      echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
done

STATE_DIR="$BARISTA_HOME/.state"

# ---------------------------------------------------------------------------
# Pretty output
# ---------------------------------------------------------------------------

if [[ -t 1 ]]; then
  BOLD="$(printf '\033[1m')"; DIM="$(printf '\033[2m')"
  RED="$(printf '\033[31m')"; GRN="$(printf '\033[32m')"
  YLW="$(printf '\033[33m')"; CYA="$(printf '\033[36m')"
  RST="$(printf '\033[0m')"
else
  BOLD=""; DIM=""; RED=""; GRN=""; YLW=""; CYA=""; RST=""
fi

log()  { printf '%s==>%s %s\n'  "$CYA" "$RST" "$*"; }
ok()   { printf '%s ✓ %s%s\n'   "$GRN" "$*" "$RST"; }
warn() { printf '%s ⚠ %s%s\n'   "$YLW" "$*" "$RST"; }
die()  { printf '%s ✗ %s%s\n'   "$RED" "$*" "$RST" >&2; exit 1; }

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '%s$ %s%s\n' "$DIM" "$*" "$RST"
  else
    eval "$@"
  fi
}

# Each step is gated by a state marker so re-running is a no-op for
# completed steps. Mark only on success.
step() {
  local name="$1" fn="$2"
  local marker="$STATE_DIR/$name.done"
  if [[ -f "$marker" ]]; then
    ok "$name (already done)"
    return 0
  fi
  log "$name"
  if "$fn"; then
    mkdir -p "$STATE_DIR"
    [[ "$DRY_RUN" == "1" ]] || touch "$marker"
    ok "$name"
  else
    die "$name failed"
  fi
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

preflight() {
  case "$(uname -s)" in
    Darwin|Linux) ;;
    *) die "Unsupported OS: $(uname -s). Barista supports macOS and Linux." ;;
  esac

  if ! command -v docker >/dev/null 2>&1; then
    warn "Docker is not installed."
    if [[ "$(uname -s)" == "Linux" ]]; then
      if [[ "$INTERACTIVE" == "1" ]]; then
        read -rp "Install Docker via get.docker.com? [y/N] " ans
        [[ "$ans" =~ ^[Yy]$ ]] || die "Docker is required."
      fi
      log "Installing Docker"
      run "curl -fsSL https://get.docker.com | sh"
      run "sudo systemctl enable --now docker || true"
    else
      die "Install Docker Desktop from https://www.docker.com/products/docker-desktop and re-run."
    fi
  fi

  if ! docker info >/dev/null 2>&1; then
    die "Docker daemon is not reachable. Start Docker and re-run."
  fi

  # disk
  local free_kb
  free_kb="$(df -k "$HOME" | awk 'NR==2 {print $4}')"
  if [[ "$free_kb" -lt $((5 * 1024 * 1024)) ]]; then
    die "Need at least 5 GB free in \$HOME (currently $((free_kb/1024/1024)) GB)."
  fi

  # ports
  for p in 80 443; do
    if [[ "$NO_TRAEFIK" == "0" ]] && lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
      warn "Port $p is in use. Traefik will fail to start until it's free."
    fi
  done
}

# ---------------------------------------------------------------------------
# Directories & env
# ---------------------------------------------------------------------------

ensure_dirs() {
  for d in \
    "$BARISTA_HOME" \
    "$BARISTA_HOME/data/mariadb" \
    "$BARISTA_HOME/data/mariadb-logs" \
    "$BARISTA_HOME/data/redis" \
    "$BARISTA_HOME/data/benches" \
    "$BARISTA_HOME/data/traefik" \
    "$BARISTA_HOME/config/mariadb" \
    "$BARISTA_HOME/config/traefik" \
    "$BARISTA_HOME/backups" \
    "$BARISTA_HOME/src" \
    "$STATE_DIR" ; do
    run "mkdir -p '$d'"
  done

  # Frappe images use uid 1000.
  # On macOS Docker Desktop maps automatically; only chown on Linux.
  if [[ "$(uname -s)" == "Linux" ]]; then
    run "sudo chown -R 1000:1000 '$BARISTA_HOME/data/benches' '$BARISTA_HOME/backups' || true"
  fi
}

random_hex() { LC_ALL=C tr -dc 'a-f0-9' </dev/urandom | head -c "${1:-32}"; }

write_env() {
  local f="$BARISTA_HOME/.env"
  if [[ -f "$f" ]]; then
    ok ".env exists, leaving it alone"
    return 0
  fi
  local mariadb_pw barista_pw
  mariadb_pw="$(random_hex 32)"
  barista_pw="$(random_hex 24)"

  local manager_token
  manager_token="$(random_hex 32)"

  cat > "$f" <<EOF
BARISTA_VERSION=0.1.0
BARISTA_MARIADB_ROOT_PASSWORD=$mariadb_pw
BARISTA_ADMIN_PASSWORD=$barista_pw
BARISTA_DOCKER_MANAGER_TOKEN=$manager_token
BARISTA_TIMEZONE=$(date +%Z)
BARISTA_HTTP_PORT_RANGE_START=$PORT_START
BARISTA_DOMAIN=$DOMAIN
BARISTA_LETSENCRYPT_EMAIL=$EMAIL
BARISTA_DOCKER_NETWORK=$NETWORK
EOF
  chmod 600 "$f"

  if [[ "$INTERACTIVE" == "1" ]]; then
    "${EDITOR:-vi}" "$f"
  fi
}

# ---------------------------------------------------------------------------
# Configs
# ---------------------------------------------------------------------------

write_mariadb_conf() {
  cat > "$BARISTA_HOME/config/mariadb/my.cnf" <<'CNF'
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

# Slow log — Barista reads this
slow_query_log = 1
slow_query_log_file = /var/log/mysql/slow.log
long_query_time = 0.5
log_queries_not_using_indexes = 0

# Bin log (off by default; Barista flips this on via Settings)
# log_bin = /var/lib/mysql/binlog
# binlog_format = ROW
# expire_logs_days = 7

[client]
default-character-set = utf8mb4
CNF
}

write_traefik_conf() {
  cat > "$BARISTA_HOME/config/traefik/traefik.yml" <<EOF
entryPoints:
  web:
    address: ":80"
  websecure:
    address: ":443"

providers:
  docker:
    exposedByDefault: false
    network: $NETWORK
  file:
    directory: /etc/traefik
    watch: true

api:
  dashboard: false

EOF
  if [[ -n "$EMAIL" && "$DOMAIN" != *.localhost ]]; then
    cat >> "$BARISTA_HOME/config/traefik/traefik.yml" <<EOF
certificatesResolvers:
  le:
    acme:
      email: $EMAIL
      storage: /data/acme.json
      tlsChallenge: {}
EOF
  fi

  # dynamic.yml is empty initially; Barista rewrites it as sites change
  : > "$BARISTA_HOME/config/traefik/dynamic.yml"
}

# ---------------------------------------------------------------------------
# docker-compose for shared services
# ---------------------------------------------------------------------------

write_compose() {
  local f="$BARISTA_HOME/docker-compose.yml"
  cat > "$f" <<EOF
name: barista
networks:
  $NETWORK:
    name: $NETWORK

services:
  mariadb:
    container_name: barista-mariadb
    image: mariadb:11
    restart: unless-stopped
    networks: [$NETWORK]
    environment:
      MARIADB_ROOT_PASSWORD: \${BARISTA_MARIADB_ROOT_PASSWORD}
    volumes:
      - $BARISTA_HOME/data/mariadb:/var/lib/mysql
      - $BARISTA_HOME/data/mariadb-logs:/var/log/mysql
      - $BARISTA_HOME/config/mariadb/my.cnf:/etc/mysql/conf.d/my.cnf:ro
    ports:
      - "127.0.0.1:13306:3306"

  redis:
    container_name: barista-redis
    image: redis:7-alpine
    restart: unless-stopped
    networks: [$NETWORK]
    volumes:
      - $BARISTA_HOME/data/redis:/data

  docker-manager:
    container_name: barista-docker-manager
    image: barista/docker-manager:local
    build:
      context: $BARISTA_HOME/src/docker-manager
    restart: unless-stopped
    networks: [$NETWORK]
    # NB: no \`ports:\` — internal network only
    environment:
      BARISTA_DOCKER_MANAGER_TOKEN: \${BARISTA_DOCKER_MANAGER_TOKEN}
      NETWORK: ${NETWORK}
      BARISTA_DATA_ROOT: /data
      BARISTA_TRAEFIK_DYNAMIC: /etc/traefik/dynamic.yml
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - $BARISTA_HOME/data:/data
      - $BARISTA_HOME/config/traefik:/etc/traefik
    labels:
      barista.role: docker-manager

EOF
  if [[ "$NO_TRAEFIK" == "0" ]]; then
    cat >> "$f" <<EOF
  traefik:
    container_name: barista-traefik
    image: traefik:v3.1
    restart: unless-stopped
    networks: [$NETWORK]
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - $BARISTA_HOME/config/traefik:/etc/traefik:ro
      - $BARISTA_HOME/data/traefik:/data
      - /var/run/docker.sock:/var/run/docker.sock:ro
EOF
  fi
}

# ---------------------------------------------------------------------------
# Stage docker-manager source for `docker compose build`
# ---------------------------------------------------------------------------

stage_docker_manager() {
  # The repo ships the docker-manager source alongside install.sh.
  # On a curl|bash install, install.sh is alone — pull source from the
  # repo if it's not next to us.
  local src_dst="$BARISTA_HOME/src/docker-manager"
  local here
  here="$(cd "$(dirname "$0")" && pwd)"
  if [[ -d "$here/docker-manager" ]]; then
    run "rsync -a --delete '$here/docker-manager/' '$src_dst/'"
  else
    log "Fetching docker-manager source from $BARISTA_REPO"
    local tmp
    tmp="$(mktemp -d)"
    run "git clone --depth 1 --branch $BARISTA_BRANCH $BARISTA_REPO '$tmp'"
    run "rsync -a --delete '$tmp/docker-manager/' '$src_dst/'"
    run "rm -rf '$tmp'"
  fi
}

# ---------------------------------------------------------------------------
# Pull & start shared services
# ---------------------------------------------------------------------------

compose_up() {
  run "docker network inspect $NETWORK >/dev/null 2>&1 || docker network create $NETWORK"
  run "cd '$BARISTA_HOME' && docker compose --env-file .env build docker-manager"
  run "cd '$BARISTA_HOME' && docker compose --env-file .env pull --ignore-pull-failures || true"
  run "cd '$BARISTA_HOME' && docker compose --env-file .env up -d"
  # wait for MariaDB
  log "Waiting for MariaDB to be ready"
  for i in $(seq 1 60); do
    if docker exec barista-mariadb sh -lc 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -e "SELECT 1"' >/dev/null 2>&1; then
      ok "MariaDB ready"
      break
    fi
    sleep 1
    [[ $i == 60 ]] && die "MariaDB did not become ready in 60s"
  done

  log "Waiting for docker-manager to be ready"
  for i in $(seq 1 30); do
    if docker exec barista-docker-manager \
       curl -fsS -H "X-Auth-Token: $BARISTA_DOCKER_MANAGER_TOKEN" \
            http://localhost:8080/v1/health >/dev/null 2>&1; then
      ok "docker-manager ready"
      return 0
    fi
    sleep 1
  done
  die "docker-manager did not become ready in 30s"
}

# ---------------------------------------------------------------------------
# Bootstrap the control-plane bench
# ---------------------------------------------------------------------------

bootstrap_cp() {
  local bench_dir="$BARISTA_HOME/data/benches/default"
  set -a; . "$BARISTA_HOME/.env"; set +a

  if [[ -d "$bench_dir/sites" ]]; then
    ok "Control-plane bench already initialised"
  else
    log "Initialising control-plane bench (one-time, takes ~3 min)"
    run "docker pull $BASE_IMAGE"

    run "docker run --rm \
      --network $NETWORK \
      -v '$bench_dir':/work \
      $BASE_IMAGE \
      bash -lc 'cd /tmp && bench init --skip-redis-config-generation --frappe-branch version-15 b && shopt -s dotglob && mv /tmp/b/* /work/'"

    # write common_site_config pointing at the shared services
    cat > "$bench_dir/sites/common_site_config.json" <<JSON
{
  "db_host": "barista-mariadb",
  "db_port": 3306,
  "redis_cache":   "redis://barista-redis:6379/0",
  "redis_queue":   "redis://barista-redis:6379/1",
  "redis_socketio":"redis://barista-redis:6379/2"
}
JSON
  fi

  if ! docker ps --format '{{.Names}}' | grep -qx 'barista-bench-default'; then
    log "Starting control-plane container"
    local extra_labels=""
    if [[ "$NO_TRAEFIK" == "0" ]]; then
      extra_labels="--label traefik.enable=true \
        --label traefik.http.routers.barista.rule=Host(\`${DOMAIN}\`) \
        --label traefik.http.services.barista.loadbalancer.server.port=80"
      if [[ -n "$EMAIL" && "$DOMAIN" != *.localhost ]]; then
        extra_labels="$extra_labels \
          --label traefik.http.routers.barista.entrypoints=websecure \
          --label traefik.http.routers.barista.tls.certresolver=le"
      fi
    fi

    run "docker run -d --name barista-bench-default \
      --network $NETWORK \
      --restart unless-stopped \
      -v '$bench_dir':/home/frappe/bench \
      -v '$BARISTA_HOME/backups':/backups \
      -v '$BARISTA_HOME/data/mariadb-logs/slow.log':/slow.log:ro \
      -p 127.0.0.1:${PORT_START}:80 \
      -e BARISTA_DOCKER_MANAGER_URL=http://barista-docker-manager:8080 \
      -e BARISTA_DOCKER_MANAGER_TOKEN=${BARISTA_DOCKER_MANAGER_TOKEN} \
      --label barista.role=control-plane \
      $extra_labels \
      $BASE_IMAGE \
      /entrypoint.sh"
  fi

  # install barista app + create site (idempotent)
  if ! docker exec -u frappe barista-bench-default \
       test -d "/home/frappe/bench/apps/barista" 2>/dev/null; then
    log "Installing Barista app"
    run "docker exec -u frappe barista-bench-default bash -lc \
      'cd /home/frappe/bench && bench get-app --branch $BARISTA_BRANCH $BARISTA_REPO'"
  fi

  if ! docker exec -u frappe barista-bench-default \
       test -f "/home/frappe/bench/sites/$DOMAIN/site_config.json" 2>/dev/null; then
    log "Creating site $DOMAIN"
    run "docker exec -u frappe barista-bench-default bash -lc \
      'cd /home/frappe/bench && bench new-site \
         --no-mariadb-socket \
         --admin-password $BARISTA_ADMIN_PASSWORD \
         --mariadb-root-password $BARISTA_MARIADB_ROOT_PASSWORD \
         --install-app barista \
         $DOMAIN'"
    run "docker exec -u frappe barista-bench-default bash -lc \
      'cd /home/frappe/bench && bench use $DOMAIN'"
    run "docker exec -u frappe barista-bench-default bash -lc \
      'cd /home/frappe/bench && bench --site $DOMAIN execute barista.install.register_control_plane'"
  fi
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print_summary() {
  set -a; . "$BARISTA_HOME/.env"; set +a
  local url
  if [[ "$DOMAIN" == *.localhost ]]; then
    url="http://$DOMAIN/barista"
  elif [[ -n "$EMAIL" ]]; then
    url="https://$DOMAIN/barista"
  else
    url="http://$DOMAIN/barista"
  fi

  cat <<EOF

${BOLD}Barista is ready ☕${RST}

  URL:        ${BOLD}$url${RST}
  Username:   Administrator
  Password:   $BARISTA_ADMIN_PASSWORD

  Bench:      barista-bench-default   (running)
  Site:       $DOMAIN                  (control-plane)
  Data dir:   $BARISTA_HOME

  ${DIM}Re-run this script any time — it is idempotent.${RST}
  ${DIM}Uninstall:   $0 --uninstall${RST}
  ${DIM}Wipe data:   $0 --purge${RST}

EOF

  if [[ "$(uname -s)" == "Darwin" ]]; then
    command -v open >/dev/null && open "$url" || true
  fi
}

# ---------------------------------------------------------------------------
# Uninstall / purge
# ---------------------------------------------------------------------------

do_uninstall() {
  log "Stopping containers"
  run "cd '$BARISTA_HOME' && docker compose --env-file .env down || true"
  run "docker ps -aq --filter label=barista.role | xargs -r docker rm -f"
  run "docker network rm $NETWORK || true"
  cat <<EOF
${GRN}Containers stopped.${RST}
Data is preserved at $BARISTA_HOME. To wipe it, run: $0 --purge
EOF
}

do_purge() {
  printf '%sThis will DELETE %s including all benches, sites, and backups.%s\n' \
    "$RED" "$BARISTA_HOME" "$RST"
  read -rp "Type 'PURGE' to confirm: " ans
  [[ "$ans" == "PURGE" ]] || die "Cancelled."
  do_uninstall
  run "rm -rf '$BARISTA_HOME'"
  ok "Purged."
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

case "$MODE" in
  uninstall) do_uninstall; exit 0 ;;
  purge)     do_purge;     exit 0 ;;
esac

mkdir -p "$STATE_DIR"

step "preflight"            preflight
step "ensure_dirs"          ensure_dirs
step "write_env"            write_env
step "write_mariadb_conf"   write_mariadb_conf
step "write_traefik_conf"   write_traefik_conf
step "stage_docker_manager" stage_docker_manager
step "write_compose"        write_compose
step "compose_up"           compose_up
step "bootstrap_cp"         bootstrap_cp

print_summary
