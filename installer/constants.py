"""Tunable defaults. Every magic number / image tag lives here."""

__version__ = "0.1.0"

# --- source repo ---
DEFAULTS_REPO = "https://github.com/rmehta/barista"
DEFAULTS_BRANCH = "main"

# --- images ---
DEFAULTS_BASE_IMAGE = "frappe/bench:latest"   # https://hub.docker.com/r/frappe/bench

# --- networking ---
DEFAULTS_NETWORK = "barista-net"
DEFAULTS_DOMAIN = "barista.localhost"
DEFAULTS_PORT_START = 18000
BENCH_INTERNAL_PORT = 8000     # bench's default gunicorn port

# --- preflight ---
MIN_FREE_GB = 5

# --- compose-up readiness ---
MARIADB_READY_TIMEOUT_S = 60
MANAGER_READY_TIMEOUT_S = 30
BENCH_HTTP_TIMEOUT_S = 120

# --- container path the long-lived bench mounts at; the venv's
# shebangs are rewritten to this so they stay valid after the move
# from the throw-away init container.
BENCH_RUNTIME_PATH = "/home/frappe/bench"
