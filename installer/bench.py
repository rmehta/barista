"""The control-plane bench container.

Everything related to creating, populating and serving
`barista-bench-default` lives here. The Installer composes a `Bench`
instance and delegates its `bootstrap_cp` step to `Bench.bootstrap`.

The bench goes through three states during install:

  1. (nothing) — host dir is empty.
  2. `bench init`-ed — host dir has Procfile, apps/frappe, sites/, env/
     (with shebangs rewritten to the runtime mount path).
  3. keep-alive container running — bench dir is mounted into
     `barista-bench-default`, container CMD is `tail -f /dev/null`,
     so we can `docker exec` `bench get-app`, `bench new-site`,
     `bench --site … execute …` into it.
  4. serving container running — same container name, but CMD is
     `bench start` so port 8000 is bound.

Steps 3 and 4 use the same Docker labels and bind mounts; only the
CMD differs. `Bench.bootstrap` walks them in order; each sub-step is
gated by a check so a re-run skips finished work.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from .config import Config
from .constants import (
    BENCH_CONTAINER_NAME,
    BENCH_HTTP_TIMEOUT_S,
    BENCH_INTERNAL_PORT,
    BENCH_RUNTIME_PATH,
)
from .docker import Docker
from .env_file import parse_env_file
from .errors import InstallerError
from .logger import Logger


class Bench:
    """The control-plane bench: one bench dir on disk + one container."""

    def __init__(self, config: Config, logger: Logger, docker: Docker):
        self.cfg = config
        self.log = logger
        self.docker = docker

    @property
    def dir(self) -> Path:
        """Host path of the bench (`~/.barista/data/benches/default`)."""
        return self.cfg.barista_home / "data" / "benches" / "default"

    @property
    def name(self) -> str:
        return BENCH_CONTAINER_NAME

    # ----- entry point -----------------------------------------------------

    def bootstrap(self) -> None:
        """Create the control-plane bench container + site + Barista app.

        Two-phase: a keep-alive container is brought up first (running
        `tail -f /dev/null`), then we docker-exec the actual `bench
        get-app` / `bench new-site` calls into it. Once setup is done
        we swap the container to `bench start` so port 8000 is being
        served.
        """
        sites_dir = self.dir / "sites"
        if not sites_dir.exists():
            self._init()
            self._write_common_site_config(sites_dir)

        if not self.docker.container_running(self.name):
            self._run_keep_alive()

        if not self._app_present():
            self._install_barista_app()
        if not self._site_present():
            self._create_site()
            self._register_control_plane()

        self._ensure_serving()

    # ----- step 1: bench init in a throw-away container --------------------

    def _init(self) -> None:
        self.log.log("Initialising control-plane bench (one-time, ~3 min)")
        # The bench container runs as uid 1000 (`frappe`); pre-create
        # the bind-mount target with that ownership, or docker creates
        # it as root and the frappe user can't write.
        self.dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "linux":
            subprocess.run(["chown", "1000:1000", str(self.dir)], check=False)
        self.docker.run(["docker", "pull", self.cfg.base_image])
        self.docker.run([
            "docker", "run", "--rm",
            "--network", self.cfg.network,
            "-v", f"{self.dir}:/work",
            self.cfg.base_image,
            "bash", "-lc", self._bench_init_cmd(),
        ])

    @staticmethod
    def _bench_init_cmd() -> str:
        """The bash one-liner the init container runs.

        `bench init` bakes absolute paths into the venv (shebangs in
        env/bin/*, executable= in env/pyvenv.cfg). We init at /tmp/b
        and move to /work, then the long-lived container mounts the
        same files at /home/frappe/bench — so we have to rewrite
        those paths or pip is unrunnable.
        """
        target = f"{BENCH_RUNTIME_PATH}/env"
        return (
            "cd /tmp && bench init --skip-redis-config-generation "
            "--frappe-branch version-15 b && "
            "shopt -s dotglob && mv /tmp/b/* /work/ && "
            "find /work/env/bin -type f -exec "
            rf"sed -i 's|/tmp/b/env|{target}|g' " + "{} + && "
            rf"sed -i 's|/tmp/b/env|{target}|g' /work/env/pyvenv.cfg"
        )

    # ----- step 2: common_site_config.json ---------------------------------

    @staticmethod
    def _write_common_site_config(sites_dir: Path) -> None:
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

    # ----- step 3: bring up the keep-alive container -----------------------

    def _run_keep_alive(self) -> None:
        """Container that stays up while we exec into it."""
        argv = self._docker_run_args() + [
            self.cfg.base_image, "tail", "-f", "/dev/null"
        ]
        self.docker.run(argv)

    def _docker_run_args(self) -> list[str]:
        """Common `docker run` args shared by keep-alive + serving."""
        env = parse_env_file(self.cfg.env_file)
        port = env.get("BARISTA_HTTP_PORT_RANGE_START", str(self.cfg.port_start))
        token = env.get("BARISTA_DOCKER_MANAGER_TOKEN", "")
        argv = [
            "docker", "run", "-d", "--name", self.name,
            "--network", self.cfg.network,
            "--restart", "unless-stopped",
            "-v", f"{self.dir}:{BENCH_RUNTIME_PATH}",
            "-v", f"{self.cfg.barista_home}/backups:/backups",
            "-p", f"127.0.0.1:{port}:{BENCH_INTERNAL_PORT}",
            "-e", "BARISTA_DOCKER_MANAGER_URL=http://barista-docker-manager:8080",
            "-e", f"BARISTA_DOCKER_MANAGER_TOKEN={token}",
            "--label", "barista.role=control-plane",
        ]
        for label in self._traefik_labels(env):
            argv += ["--label", label]
        return argv

    def _traefik_labels(self, env: dict[str, str]) -> list[str]:
        if self.cfg.no_traefik:
            return []
        domain = env.get("BARISTA_DOMAIN", self.cfg.domain)
        labels = [
            "traefik.enable=true",
            f"traefik.http.routers.barista.rule=Host(`{domain}`)",
            f"traefik.http.services.barista.loadbalancer.server.port={BENCH_INTERNAL_PORT}",
        ]
        if self.cfg.email and not domain.endswith(".localhost"):
            labels += [
                "traefik.http.routers.barista.entrypoints=websecure",
                "traefik.http.routers.barista.tls.certresolver=le",
            ]
        return labels

    # ----- step 4: bench setup via docker exec -----------------------------

    def _app_present(self) -> bool:
        r = subprocess.run(
            ["docker", "exec", "-u", "frappe", self.name,
             "test", "-d", f"{BENCH_RUNTIME_PATH}/apps/barista"],
            capture_output=True, check=False,
        )
        return r.returncode == 0

    def _install_barista_app(self) -> None:
        self.log.log("Installing Barista app")
        self._exec_in_bench(
            f"bench get-app --branch {self.cfg.branch} {self.cfg.repo}"
        )

    def _site_present(self) -> bool:
        domain = self._domain()
        r = subprocess.run(
            ["docker", "exec", "-u", "frappe", self.name,
             "test", "-f", f"{BENCH_RUNTIME_PATH}/sites/{domain}/site_config.json"],
            capture_output=True, check=False,
        )
        return r.returncode == 0

    def _create_site(self) -> None:
        env = parse_env_file(self.cfg.env_file)
        domain = env.get("BARISTA_DOMAIN", self.cfg.domain)
        self.log.log(f"Creating site {domain}")
        self._exec_in_bench(
            "bench new-site --no-mariadb-socket "
            f"--admin-password {env['BARISTA_ADMIN_PASSWORD']} "
            f"--mariadb-root-password {env['BARISTA_MARIADB_ROOT_PASSWORD']} "
            "--install-app barista "
            f"{domain}"
        )

    def _register_control_plane(self) -> None:
        domain = self._domain()
        self._exec_in_bench(
            f"bench use {domain} && "
            f"bench --site {domain} execute barista.install.register_control_plane"
        )

    def _exec_in_bench(self, bash_cmd: str) -> None:
        """Run `bash -lc <cmd>` as the frappe user, cwd=bench dir."""
        self.docker.run([
            "docker", "exec", "-u", "frappe", self.name,
            "bash", "-lc", f"cd {BENCH_RUNTIME_PATH} && {bash_cmd}",
        ])

    def _domain(self) -> str:
        env = parse_env_file(self.cfg.env_file)
        return env.get("BARISTA_DOMAIN", self.cfg.domain)

    # ----- step 5: swap to `bench start` -----------------------------------

    def _ensure_serving(self) -> None:
        """Swap the container from `tail` to `bench start`. Idempotent."""
        if self._is_serving():
            return
        self.log.log("Switching control-plane bench to `bench start`")
        self.docker.run(["docker", "rm", "-f", self.name], check=False)
        self._run_serving()
        self._wait_for_http()

    def _is_serving(self) -> bool:
        """True if the running container's CMD includes `bench`."""
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Config.Cmd}}", self.name],
            capture_output=True, text=True, check=False,
        )
        return r.returncode == 0 and '"bench"' in (r.stdout or "")

    def _run_serving(self) -> None:
        """Final container with `bench start` as PID 1."""
        argv = self._docker_run_args() + [
            self.cfg.base_image, "bash", "-lc",
            f"cd {BENCH_RUNTIME_PATH} && exec bench start",
        ]
        self.docker.run(argv)

    def _wait_for_http(self) -> None:
        self.log.log(f"Waiting for bench to serve on :{BENCH_INTERNAL_PORT}")
        deadline = time.time() + BENCH_HTTP_TIMEOUT_S
        cmd = ["docker", "exec", self.name, "curl", "-fsS",
               f"http://localhost:{BENCH_INTERNAL_PORT}/api/method/ping"]
        while time.time() < deadline:
            r = subprocess.run(cmd, capture_output=True, check=False)
            if r.returncode == 0:
                self.log.ok("Bench is serving")
                return
            time.sleep(2)
        raise InstallerError("bench did not start serving in time")
