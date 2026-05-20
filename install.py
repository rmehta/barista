#!/usr/bin/env python3
"""Barista installer (Python edition).

Sets up Barista on a fresh host:
  - Docker (if missing, on Linux only)
  - Shared services: MariaDB, Redis, Traefik, barista-docker-manager
  - The first bench + the `barista.localhost` site

Usage:
    curl -fsSL https://raw.githubusercontent.com/rmehta/barista/main/install.py | python3 -
    ./install.py [--domain HOST] [--email ADDR] [--port-start N]
                 [--interactive] [--dry-run]
                 [--uninstall | --purge]

Idempotent: re-running is safe. Each step writes a marker under
~/.barista/.state/ on success; subsequent runs skip done steps.

Design notes:
- **Stdlib only.** So `curl ... | python3 -` Just Works. We shell out
  to the `docker` CLI rather than depending on the Docker SDK.
- **OO with small methods.** Each installer step is one method on
  `Installer`. They take no positional args (config is on self) so
  they're easy to call from tests in any order.
- **Pure where possible.** Everything that *renders* a config file is
  a separate method that returns a string; the only impure method is
  the one that writes it. Same goes for command lines — we build the
  list, then a single `Docker.run_cmd` executes it.

See ../specs/06-install-and-bootstrap.md for the spec.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

__version__ = "0.1.0"

DEFAULTS_REPO = "https://github.com/rmehta/barista"
DEFAULTS_BRANCH = "main"
DEFAULTS_BASE_IMAGE = "ghcr.io/frappe/bench-base:python3.11-node20"
DEFAULTS_NETWORK = "barista-net"
DEFAULTS_DOMAIN = "barista.localhost"
DEFAULTS_PORT_START = 18000
MIN_FREE_GB = 5
MARIADB_READY_TIMEOUT_S = 60
MANAGER_READY_TIMEOUT_S = 30


# ============================================================================
# Logger — colourful, but degrades gracefully when stdout is not a tty.
# ============================================================================

class Logger:
    """Pretty terminal output. Stateless except for an isatty flag."""

    COLORS_TTY = {
        "BOLD": "\033[1m", "DIM": "\033[2m",
        "RED": "\033[31m", "GRN": "\033[32m",
        "YLW": "\033[33m", "CYA": "\033[36m",
        "RST": "\033[0m",
    }
    COLORS_NONE = {k: "" for k in COLORS_TTY}

    def __init__(self, stream=sys.stdout, isatty: bool | None = None):
        self._stream = stream
        if isatty is None:
            isatty = hasattr(stream, "isatty") and stream.isatty()
        self.c = self.COLORS_TTY if isatty else self.COLORS_NONE

    def log(self, msg: str) -> None:
        self._stream.write(f"{self.c['CYA']}==>{self.c['RST']} {msg}\n")

    def ok(self, msg: str) -> None:
        self._stream.write(f"{self.c['GRN']} ✓ {msg}{self.c['RST']}\n")

    def warn(self, msg: str) -> None:
        self._stream.write(f"{self.c['YLW']} ⚠ {msg}{self.c['RST']}\n")

    def err(self, msg: str) -> None:
        self._stream.write(f"{self.c['RED']} ✗ {msg}{self.c['RST']}\n")

    def cmd(self, argv: list[str]) -> None:
        self._stream.write(f"{self.c['DIM']}$ {' '.join(argv)}{self.c['RST']}\n")


class InstallerError(Exception):
    """Anything we can't recover from. main() catches + exits 1."""


# ============================================================================
# Config — flags + computed paths.
# ============================================================================

@dataclass
class Config:
    """Everything the installer reads. Built once from argv + env."""

    mode: str = "install"          # install | uninstall | purge
    barista_home: Path = field(
        default_factory=lambda: Path(os.environ.get("BARISTA_HOME") or
                                      Path.home() / ".barista")
    )
    repo: str = DEFAULTS_REPO
    branch: str = DEFAULTS_BRANCH
    base_image: str = DEFAULTS_BASE_IMAGE
    network: str = DEFAULTS_NETWORK
    domain: str = DEFAULTS_DOMAIN
    email: str = ""
    port_start: int = DEFAULTS_PORT_START
    interactive: bool = False
    dry_run: bool = False
    no_traefik: bool = False
    script_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent)

    # ---- derived paths ----

    @property
    def state_dir(self) -> Path:
        return self.barista_home / ".state"

    @property
    def env_file(self) -> Path:
        return self.barista_home / ".env"

    @property
    def src_dir(self) -> Path:
        return self.barista_home / "src" / "docker-manager"

    @property
    def compose_file(self) -> Path:
        return self.barista_home / "docker-compose.yml"

    @property
    def data_dirs(self) -> list[Path]:
        h = self.barista_home
        return [
            h, h / "data" / "mariadb", h / "data" / "mariadb-logs",
            h / "data" / "redis", h / "data" / "benches", h / "data" / "traefik",
            h / "config" / "mariadb", h / "config" / "traefik",
            h / "backups", h / "src", self.state_dir,
        ]

    # ---- factory ----

    @classmethod
    def from_argv(cls, argv: list[str]) -> Config:
        p = argparse.ArgumentParser(
            prog="install.py",
            description="Install Barista on this host.",
        )
        p.add_argument("--domain", default=DEFAULTS_DOMAIN)
        p.add_argument("--email", default="")
        p.add_argument("--port-start", type=int, default=DEFAULTS_PORT_START)
        p.add_argument("--no-traefik", action="store_true")
        p.add_argument("--interactive", action="store_true")
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--repo", default=DEFAULTS_REPO)
        p.add_argument("--branch", default=DEFAULTS_BRANCH)

        mode = p.add_mutually_exclusive_group()
        mode.add_argument("--uninstall", dest="mode_uninstall", action="store_true")
        mode.add_argument("--purge",     dest="mode_purge",     action="store_true")

        args = p.parse_args(argv)
        return cls(
            mode=("purge" if args.mode_purge else
                  "uninstall" if args.mode_uninstall else "install"),
            domain=args.domain,
            email=args.email,
            port_start=args.port_start,
            no_traefik=args.no_traefik,
            interactive=args.interactive,
            dry_run=args.dry_run,
            repo=args.repo,
            branch=args.branch,
        )


# ============================================================================
# Secrets — a tiny helper, monkey-patched in tests for determinism.
# ============================================================================

def random_hex(nbytes: int = 16) -> str:
    return secrets.token_hex(nbytes)


# ============================================================================
# Docker — a thin wrapper around the `docker` CLI.
# Honours dry-run and exposes one mockable seam (`run`) for tests.
# ============================================================================

class Docker:
    def __init__(self, logger: Logger, dry_run: bool = False):
        self.log = logger
        self.dry_run = dry_run

    def run(self, argv: list[str], capture: bool = False,
            check: bool = True, timeout: int | None = None,
            stdin: str | None = None) -> subprocess.CompletedProcess:
        """Single seam for every external command."""
        self.log.cmd(argv)
        if self.dry_run:
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.run(
            argv,
            capture_output=capture,
            check=check,
            text=True,
            input=stdin,
            timeout=timeout,
        )

    # ---- queries (always live; dry-run still reports truthfully) ----

    def daemon_up(self) -> bool:
        try:
            return subprocess.run(
                ["docker", "info"], capture_output=True, check=False
            ).returncode == 0
        except FileNotFoundError:
            return False

    def installed(self) -> bool:
        return shutil.which("docker") is not None

    def network_exists(self, name: str) -> bool:
        r = subprocess.run(
            ["docker", "network", "inspect", name],
            capture_output=True, check=False,
        )
        return r.returncode == 0

    def container_running(self, name: str) -> bool:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, check=False, text=True,
        )
        if r.returncode != 0:
            return False
        return name in r.stdout.split()


# ============================================================================
# StepRunner — runs ordered steps, gates each by a state marker.
# ============================================================================

class StepRunner:
    def __init__(self, state_dir: Path, logger: Logger, dry_run: bool = False):
        self.state_dir = state_dir
        self.log = logger
        self.dry_run = dry_run
        self._steps: list[tuple[str, Callable[[], None]]] = []

    def add(self, name: str, fn: Callable[[], None]) -> None:
        self._steps.append((name, fn))

    def marker(self, name: str) -> Path:
        return self.state_dir / f"{name}.done"

    def is_done(self, name: str) -> bool:
        return self.marker(name).exists()

    def run(self) -> None:
        for name, fn in self._steps:
            if self.is_done(name):
                self.log.ok(f"{name} (already done)")
                continue
            self.log.log(name)
            try:
                fn()
            except Exception as e:
                self.log.err(f"{name} failed: {e}")
                raise
            if not self.dry_run:
                self.state_dir.mkdir(parents=True, exist_ok=True)
                self.marker(name).touch()
            self.log.ok(name)


# ============================================================================
# Templates — pure functions that build config-file contents.
# Easy to unit-test: input → string.
# ============================================================================

class Templates:
    @staticmethod
    def mariadb_cnf() -> str:
        return (
            "[mysqld]\n"
            "character-set-client-handshake = FALSE\n"
            "character-set-server = utf8mb4\n"
            "collation-server = utf8mb4_unicode_ci\n"
            "\n"
            "# Slow log — Barista reads this\n"
            "slow_query_log = 1\n"
            "slow_query_log_file = /var/log/mysql/slow.log\n"
            "long_query_time = 0.5\n"
            "log_queries_not_using_indexes = 0\n"
            "\n"
            "# Bin log (off by default; Barista flips this on via Settings)\n"
            "# log_bin = /var/lib/mysql/binlog\n"
            "# binlog_format = ROW\n"
            "# expire_logs_days = 7\n"
            "\n"
            "[client]\n"
            "default-character-set = utf8mb4\n"
        )

    @staticmethod
    def traefik_yml(network: str, email: str, domain: str) -> str:
        base = (
            "entryPoints:\n"
            "  web:\n"
            "    address: \":80\"\n"
            "  websecure:\n"
            "    address: \":443\"\n"
            "\n"
            "providers:\n"
            "  docker:\n"
            "    exposedByDefault: false\n"
            f"    network: {network}\n"
            "  file:\n"
            "    directory: /etc/traefik\n"
            "    watch: true\n"
            "\n"
            "api:\n"
            "  dashboard: false\n"
        )
        if email and not domain.endswith(".localhost"):
            base += (
                "\ncertificatesResolvers:\n"
                "  le:\n"
                "    acme:\n"
                f"      email: {email}\n"
                "      storage: /data/acme.json\n"
                "      tlsChallenge: {}\n"
            )
        return base

    @staticmethod
    def env_file(*, mariadb_pw: str, barista_pw: str, manager_token: str,
                  timezone: str, port_start: int, domain: str,
                  email: str, network: str) -> str:
        return (
            f"BARISTA_VERSION={__version__}\n"
            f"BARISTA_MARIADB_ROOT_PASSWORD={mariadb_pw}\n"
            f"BARISTA_ADMIN_PASSWORD={barista_pw}\n"
            f"BARISTA_DOCKER_MANAGER_TOKEN={manager_token}\n"
            f"BARISTA_TIMEZONE={timezone}\n"
            f"BARISTA_HTTP_PORT_RANGE_START={port_start}\n"
            f"BARISTA_DOMAIN={domain}\n"
            f"BARISTA_LETSENCRYPT_EMAIL={email}\n"
            f"BARISTA_DOCKER_NETWORK={network}\n"
        )

    @staticmethod
    def compose_yml(*, home: str, network: str, no_traefik: bool) -> str:
        body = [
            "name: barista",
            "networks:",
            f"  {network}:",
            f"    name: {network}",
            "",
            "services:",
            "  mariadb:",
            "    container_name: barista-mariadb",
            "    image: mariadb:11",
            "    restart: unless-stopped",
            f"    networks: [{network}]",
            "    environment:",
            "      MARIADB_ROOT_PASSWORD: ${BARISTA_MARIADB_ROOT_PASSWORD}",
            "    volumes:",
            f"      - {home}/data/mariadb:/var/lib/mysql",
            f"      - {home}/data/mariadb-logs:/var/log/mysql",
            f"      - {home}/config/mariadb/my.cnf:/etc/mysql/conf.d/my.cnf:ro",
            "    ports:",
            "      - \"127.0.0.1:13306:3306\"",
            "",
            "  redis:",
            "    container_name: barista-redis",
            "    image: redis:7-alpine",
            "    restart: unless-stopped",
            f"    networks: [{network}]",
            "    volumes:",
            f"      - {home}/data/redis:/data",
            "",
            "  docker-manager:",
            "    container_name: barista-docker-manager",
            "    image: barista/docker-manager:local",
            "    build:",
            f"      context: {home}/src/docker-manager",
            "    restart: unless-stopped",
            f"    networks: [{network}]",
            "    environment:",
            "      BARISTA_DOCKER_MANAGER_TOKEN: ${BARISTA_DOCKER_MANAGER_TOKEN}",
            f"      NETWORK: {network}",
            "      BARISTA_DATA_ROOT: /data",
            "      BARISTA_TRAEFIK_DYNAMIC: /etc/traefik/dynamic.yml",
            "    volumes:",
            "      - /var/run/docker.sock:/var/run/docker.sock",
            f"      - {home}/data:/data",
            f"      - {home}/config/traefik:/etc/traefik",
            "    labels:",
            "      barista.role: docker-manager",
        ]
        if not no_traefik:
            body += [
                "",
                "  traefik:",
                "    container_name: barista-traefik",
                "    image: traefik:v3.1",
                "    restart: unless-stopped",
                f"    networks: [{network}]",
                "    ports:",
                "      - \"80:80\"",
                "      - \"443:443\"",
                "    volumes:",
                f"      - {home}/config/traefik:/etc/traefik:ro",
                f"      - {home}/data/traefik:/data",
                "      - /var/run/docker.sock:/var/run/docker.sock:ro",
            ]
        return "\n".join(body) + "\n"


# ============================================================================
# Installer — the actual steps. One method per step, all idempotent.
# ============================================================================

class Installer:
    """All steps are public so tests can call any of them independently."""

    def __init__(self, config: Config, logger: Logger,
                  docker: Docker | None = None):
        self.cfg = config
        self.log = logger
        self.docker = docker or Docker(logger, dry_run=config.dry_run)

    # ---------------- step 1: preflight ----------------

    def preflight(self) -> None:
        self._check_os()
        if not self.docker.installed():
            self._install_docker_or_die()
        if not self.docker.daemon_up():
            raise InstallerError(
                "Docker daemon is not reachable. Start Docker and re-run."
            )
        self._check_disk()
        self._check_ports()

    def _check_os(self) -> None:
        if sys.platform not in ("linux", "darwin"):
            raise InstallerError(
                f"Unsupported OS: {sys.platform}. Barista supports macOS and Linux."
            )

    def _install_docker_or_die(self) -> None:
        if sys.platform != "linux":
            raise InstallerError(
                "Install Docker Desktop from "
                "https://www.docker.com/products/docker-desktop and re-run."
            )
        if self.cfg.interactive:
            ans = input("Install Docker via get.docker.com? [y/N] ")
            if ans.lower() != "y":
                raise InstallerError("Docker is required.")
        self.log.log("Installing Docker (rootless install where possible)")
        self.docker.run(["bash", "-c",
                          "curl -fsSL https://get.docker.com | sh"])

    def _check_disk(self) -> None:
        free = shutil.disk_usage(str(Path.home())).free
        if free < MIN_FREE_GB * 1024**3:
            raise InstallerError(
                f"Need at least {MIN_FREE_GB} GB free in $HOME "
                f"(currently {free // 1024**3} GB)."
            )

    def _check_ports(self) -> None:
        if self.cfg.no_traefik:
            return
        import socket
        for port in (80, 443):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    self.log.warn(
                        f"Port {port} is in use. Traefik will fail to "
                        f"start until it's free."
                    )

    # ---------------- step 2: ensure_dirs ----------------

    def ensure_dirs(self) -> None:
        for d in self.cfg.data_dirs:
            d.mkdir(parents=True, exist_ok=True)
        if sys.platform == "linux":
            # Frappe images use uid 1000.
            for d in (self.cfg.barista_home / "data" / "benches",
                      self.cfg.barista_home / "backups"):
                self.docker.run(
                    ["sudo", "chown", "-R", "1000:1000", str(d)],
                    check=False,
                )

    # ---------------- step 3: write_env (one-time) ----------------

    def write_env(self) -> None:
        if self.cfg.env_file.exists():
            self.log.ok(".env exists, leaving it alone")
            return
        contents = Templates.env_file(
            mariadb_pw=random_hex(32),
            barista_pw=random_hex(24),
            manager_token=random_hex(32),
            timezone=time.tzname[0],
            port_start=self.cfg.port_start,
            domain=self.cfg.domain,
            email=self.cfg.email,
            network=self.cfg.network,
        )
        self.cfg.env_file.write_text(contents)
        self.cfg.env_file.chmod(0o600)

    # ---------------- step 4: write_mariadb_conf ----------------

    def write_mariadb_conf(self) -> None:
        (self.cfg.barista_home / "config" / "mariadb" / "my.cnf").write_text(
            Templates.mariadb_cnf()
        )

    # ---------------- step 5: write_traefik_conf ----------------

    def write_traefik_conf(self) -> None:
        cfg_dir = self.cfg.barista_home / "config" / "traefik"
        (cfg_dir / "traefik.yml").write_text(
            Templates.traefik_yml(self.cfg.network, self.cfg.email, self.cfg.domain)
        )
        # empty dynamic.yml; Barista rewrites it as sites change
        (cfg_dir / "dynamic.yml").touch()

    # ---------------- step 6: stage_docker_manager ----------------

    def stage_docker_manager(self) -> None:
        """Copy docker-manager source to ~/.barista/src/docker-manager.

        If install.py is being executed from a local checkout (the
        usual dev case), copy from there. If it's a `curl|python3`
        invocation we don't have local sources, so git clone the repo.
        """
        dst = self.cfg.src_dir
        local = self.cfg.script_dir / "docker-manager"
        if local.exists():
            self._rsync_local(local, dst)
            return
        self._git_clone_into(dst)

    def _rsync_local(self, src: Path, dst: Path) -> None:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    def _git_clone_into(self, dst: Path) -> None:
        if shutil.which("git") is None:
            raise InstallerError("git is required to fetch docker-manager source")
        tmp = self.cfg.barista_home / ".tmp-clone"
        if tmp.exists():
            shutil.rmtree(tmp)
        self.docker.run(
            ["git", "clone", "--depth", "1", "--branch", self.cfg.branch,
             self.cfg.repo, str(tmp)]
        )
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(tmp / "docker-manager", dst)
        shutil.rmtree(tmp)

    # ---------------- step 7: write_compose ----------------

    def write_compose(self) -> None:
        self.cfg.compose_file.write_text(
            Templates.compose_yml(
                home=str(self.cfg.barista_home),
                network=self.cfg.network,
                no_traefik=self.cfg.no_traefik,
            )
        )

    # ---------------- step 8: compose_up ----------------

    def compose_up(self) -> None:
        if not self.docker.network_exists(self.cfg.network):
            self.docker.run(["docker", "network", "create", self.cfg.network])

        envf = ["--env-file", str(self.cfg.env_file)]
        self.docker.run(
            ["docker", "compose", "--project-directory", str(self.cfg.barista_home),
             *envf, "build", "docker-manager"]
        )
        self.docker.run(
            ["docker", "compose", "--project-directory", str(self.cfg.barista_home),
             *envf, "pull", "--ignore-pull-failures"],
            check=False,
        )
        self.docker.run(
            ["docker", "compose", "--project-directory", str(self.cfg.barista_home),
             *envf, "up", "-d"]
        )

        self._wait_mariadb()
        self._wait_docker_manager()

    def _wait_mariadb(self) -> None:
        self.log.log("Waiting for MariaDB to be ready")
        deadline = time.time() + MARIADB_READY_TIMEOUT_S
        cmd = ["docker", "exec", "barista-mariadb", "sh", "-lc",
               'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -e "SELECT 1"']
        while time.time() < deadline:
            r = subprocess.run(cmd, capture_output=True, check=False)
            if r.returncode == 0:
                self.log.ok("MariaDB ready")
                return
            time.sleep(1)
        raise InstallerError("MariaDB did not become ready in time")

    def _wait_docker_manager(self) -> None:
        env = _parse_env_file(self.cfg.env_file)
        token = env.get("BARISTA_DOCKER_MANAGER_TOKEN", "")
        self.log.log("Waiting for docker-manager to be ready")
        deadline = time.time() + MANAGER_READY_TIMEOUT_S
        cmd = ["docker", "exec", "barista-docker-manager", "curl", "-fsS",
               "-H", f"X-Auth-Token: {token}",
               "http://localhost:8080/v1/health"]
        while time.time() < deadline:
            r = subprocess.run(cmd, capture_output=True, check=False)
            if r.returncode == 0:
                self.log.ok("docker-manager ready")
                return
            time.sleep(1)
        raise InstallerError("docker-manager did not become ready in time")

    # ---------------- step 9: bootstrap_cp ----------------

    def bootstrap_cp(self) -> None:
        """Create the control-plane bench container + site + Barista app."""
        bench_dir = self.cfg.barista_home / "data" / "benches" / "default"
        sites_dir = bench_dir / "sites"
        if not sites_dir.exists():
            self._init_bench(bench_dir)
            self._write_common_site_config(sites_dir)

        if not self.docker.container_running("barista-bench-default"):
            self._run_control_plane(bench_dir)

        if not self._app_present_in_bench():
            self._get_app()
        if not self._site_present():
            self._new_site()
            self._register_control_plane()

    def _init_bench(self, bench_dir: Path) -> None:
        self.log.log("Initialising control-plane bench (one-time, ~3 min)")
        self.docker.run(["docker", "pull", self.cfg.base_image])
        self.docker.run([
            "docker", "run", "--rm",
            "--network", self.cfg.network,
            "-v", f"{bench_dir}:/work",
            self.cfg.base_image,
            "bash", "-lc",
            "cd /tmp && bench init --skip-redis-config-generation "
            "--frappe-branch version-15 b && shopt -s dotglob && mv /tmp/b/* /work/",
        ])

    def _write_common_site_config(self, sites_dir: Path) -> None:
        sites_dir.mkdir(parents=True, exist_ok=True)
        (sites_dir / "common_site_config.json").write_text(
            '{\n'
            '  "db_host": "barista-mariadb",\n'
            '  "db_port": 3306,\n'
            '  "redis_cache":   "redis://barista-redis:6379/0",\n'
            '  "redis_queue":   "redis://barista-redis:6379/1",\n'
            '  "redis_socketio":"redis://barista-redis:6379/2"\n'
            '}\n'
        )

    def _run_control_plane(self, bench_dir: Path) -> None:
        env = _parse_env_file(self.cfg.env_file)
        port = env.get("BARISTA_HTTP_PORT_RANGE_START", str(self.cfg.port_start))
        token = env.get("BARISTA_DOCKER_MANAGER_TOKEN", "")
        labels = self._control_plane_labels(env)
        argv = [
            "docker", "run", "-d", "--name", "barista-bench-default",
            "--network", self.cfg.network,
            "--restart", "unless-stopped",
            "-v", f"{bench_dir}:/home/frappe/bench",
            "-v", f"{self.cfg.barista_home}/backups:/backups",
            "-p", f"127.0.0.1:{port}:80",
            "-e", "BARISTA_DOCKER_MANAGER_URL=http://barista-docker-manager:8080",
            "-e", f"BARISTA_DOCKER_MANAGER_TOKEN={token}",
            "--label", "barista.role=control-plane",
        ]
        for label in labels:
            argv += ["--label", label]
        argv += [self.cfg.base_image, "/entrypoint.sh"]
        self.docker.run(argv)

    def _control_plane_labels(self, env: dict[str, str]) -> list[str]:
        if self.cfg.no_traefik:
            return []
        domain = env.get("BARISTA_DOMAIN", self.cfg.domain)
        labels = [
            "traefik.enable=true",
            f"traefik.http.routers.barista.rule=Host(`{domain}`)",
            "traefik.http.services.barista.loadbalancer.server.port=80",
        ]
        if self.cfg.email and not domain.endswith(".localhost"):
            labels += [
                "traefik.http.routers.barista.entrypoints=websecure",
                "traefik.http.routers.barista.tls.certresolver=le",
            ]
        return labels

    def _app_present_in_bench(self) -> bool:
        r = subprocess.run(
            ["docker", "exec", "-u", "frappe", "barista-bench-default",
             "test", "-d", "/home/frappe/bench/apps/barista"],
            capture_output=True, check=False,
        )
        return r.returncode == 0

    def _get_app(self) -> None:
        self.log.log("Installing Barista app")
        self.docker.run([
            "docker", "exec", "-u", "frappe", "barista-bench-default",
            "bash", "-lc",
            f"cd /home/frappe/bench && bench get-app --branch {self.cfg.branch} {self.cfg.repo}",
        ])

    def _site_present(self) -> bool:
        env = _parse_env_file(self.cfg.env_file)
        domain = env.get("BARISTA_DOMAIN", self.cfg.domain)
        r = subprocess.run(
            ["docker", "exec", "-u", "frappe", "barista-bench-default",
             "test", "-f", f"/home/frappe/bench/sites/{domain}/site_config.json"],
            capture_output=True, check=False,
        )
        return r.returncode == 0

    def _new_site(self) -> None:
        env = _parse_env_file(self.cfg.env_file)
        domain = env.get("BARISTA_DOMAIN", self.cfg.domain)
        self.log.log(f"Creating site {domain}")
        self.docker.run([
            "docker", "exec", "-u", "frappe", "barista-bench-default",
            "bash", "-lc",
            "cd /home/frappe/bench && bench new-site "
            "--no-mariadb-socket "
            f"--admin-password {env['BARISTA_ADMIN_PASSWORD']} "
            f"--mariadb-root-password {env['BARISTA_MARIADB_ROOT_PASSWORD']} "
            "--install-app barista "
            f"{domain}",
        ])

    def _register_control_plane(self) -> None:
        env = _parse_env_file(self.cfg.env_file)
        domain = env.get("BARISTA_DOMAIN", self.cfg.domain)
        self.docker.run([
            "docker", "exec", "-u", "frappe", "barista-bench-default",
            "bash", "-lc",
            f"cd /home/frappe/bench && bench use {domain} && "
            f"bench --site {domain} execute barista.install.register_control_plane",
        ])

    # ---------------- summary ----------------

    def print_summary(self) -> None:
        env = _parse_env_file(self.cfg.env_file)
        domain = env.get("BARISTA_DOMAIN", self.cfg.domain)
        scheme = "https" if (self.cfg.email and not domain.endswith(".localhost")) else "http"
        url = f"{scheme}://{domain}/barista"
        admin = env.get("BARISTA_ADMIN_PASSWORD", "(see ~/.barista/.env)")
        print(
            f"\n{self.log.c['BOLD']}Barista is ready ☕{self.log.c['RST']}\n\n"
            f"  URL:        {self.log.c['BOLD']}{url}{self.log.c['RST']}\n"
            f"  Username:   Administrator\n"
            f"  Password:   {admin}\n\n"
            f"  Bench:      barista-bench-default   (running)\n"
            f"  Site:       {domain}                  (control-plane)\n"
            f"  Data dir:   {self.cfg.barista_home}\n\n"
            f"  {self.log.c['DIM']}Re-run this script any time — it is idempotent.{self.log.c['RST']}\n"
            f"  {self.log.c['DIM']}Uninstall:   {sys.argv[0]} --uninstall{self.log.c['RST']}\n"
            f"  {self.log.c['DIM']}Wipe data:   {sys.argv[0]} --purge{self.log.c['RST']}\n"
        )

    # ---------------- uninstall / purge ----------------

    def uninstall(self) -> None:
        self.log.log("Stopping containers")
        envf = ["--env-file", str(self.cfg.env_file)]
        self.docker.run(
            ["docker", "compose", "--project-directory", str(self.cfg.barista_home),
             *envf, "down"],
            check=False,
        )
        # also stop anything else labelled `barista.role`
        r = subprocess.run(
            ["docker", "ps", "-aq", "--filter", "label=barista.role"],
            capture_output=True, check=False, text=True,
        )
        ids = [i for i in r.stdout.split() if i]
        if ids:
            self.docker.run(["docker", "rm", "-f", *ids], check=False)
        self.docker.run(["docker", "network", "rm", self.cfg.network], check=False)
        self.log.ok(f"Containers stopped. Data preserved at {self.cfg.barista_home}.")

    def purge(self) -> None:
        if self.cfg.interactive:
            ans = input(f"Type 'PURGE' to delete {self.cfg.barista_home}: ")
            if ans != "PURGE":
                raise InstallerError("Cancelled.")
        self.uninstall()
        if self.cfg.barista_home.exists():
            shutil.rmtree(self.cfg.barista_home)
        self.log.ok("Purged.")


# ============================================================================
# Helpers
# ============================================================================

def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def build_install_steps(installer: Installer) -> list[tuple[str, Callable[[], None]]]:
    """List of (name, fn) pairs for an install run. Centralised so the
    StepRunner can iterate it and tests can inspect ordering."""
    i = installer
    return [
        ("preflight",            i.preflight),
        ("ensure_dirs",          i.ensure_dirs),
        ("write_env",            i.write_env),
        ("write_mariadb_conf",   i.write_mariadb_conf),
        ("write_traefik_conf",   i.write_traefik_conf),
        ("stage_docker_manager", i.stage_docker_manager),
        ("write_compose",        i.write_compose),
        ("compose_up",           i.compose_up),
        ("bootstrap_cp",         i.bootstrap_cp),
    ]


# ============================================================================
# main
# ============================================================================

def main(argv: list[str] | None = None) -> int:
    config = Config.from_argv(argv if argv is not None else sys.argv[1:])
    logger = Logger()
    installer = Installer(config, logger)

    try:
        if config.mode == "uninstall":
            installer.uninstall()
            return 0
        if config.mode == "purge":
            installer.purge()
            return 0

        runner = StepRunner(config.state_dir, logger, dry_run=config.dry_run)
        for name, fn in build_install_steps(installer):
            runner.add(name, fn)
        runner.run()
        installer.print_summary()
        return 0
    except InstallerError as e:
        logger.err(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
