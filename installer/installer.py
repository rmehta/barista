"""The `Installer` class — one public method per install step.

Every step is idempotent on its own; the StepRunner orchestrates the
ordering and the marker-based skip-if-done semantics.

The class is organised in source order matching the install order:

    preflight
    ensure_dirs
    write_env
    write_mariadb_conf
    write_traefik_conf
    stage_docker_manager
    write_compose
    compose_up
    bootstrap_cp        — delegates to Bench (see bench.py)

Plus three meta-steps:

    print_summary    — last thing on a happy install
    uninstall        — stop containers, leave data
    purge            — like uninstall + delete BARISTA_HOME
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import secrets  # accessed as secrets.random_hex so tests can monkeypatch
from .bench import Bench
from .config import Config
from .constants import (
    MANAGER_READY_TIMEOUT_S,
    MARIADB_READY_TIMEOUT_S,
    MIN_FREE_GB,
)
from .docker import Docker
from .env_file import parse_env_file
from .errors import InstallerError
from .logger import Logger
from .templates import Templates


class Installer:
    """All steps are public so tests can call any of them independently."""

    def __init__(self, config: Config, logger: Logger,
                  docker: Docker | None = None):
        self.cfg = config
        self.log = logger
        self.docker = docker or Docker(logger, dry_run=config.dry_run)
        self.bench = Bench(self.cfg, self.log, self.docker)

    # ----- step 1: preflight ------------------------------------------------

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
        for port in (80, 443):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    self.log.warn(
                        f"Port {port} is in use. Traefik will fail to "
                        f"start until it's free."
                    )

    # ----- step 2: ensure_dirs ----------------------------------------------

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

    # ----- step 3: write_env (one-time) -------------------------------------

    def write_env(self) -> None:
        if self.cfg.env_file.exists():
            self.log.ok(".env exists, leaving it alone")
            return
        contents = Templates.env_file(
            mariadb_pw=secrets.random_hex(32),
            barista_pw=secrets.random_hex(24),
            manager_token=secrets.random_hex(32),
            timezone=time.tzname[0],
            port_start=self.cfg.port_start,
            domain=self.cfg.domain,
            email=self.cfg.email,
            network=self.cfg.network,
        )
        self.cfg.env_file.write_text(contents)
        self.cfg.env_file.chmod(0o600)

    # ----- step 4: write_mariadb_conf ---------------------------------------

    def write_mariadb_conf(self) -> None:
        (self.cfg.barista_home / "config" / "mariadb" / "my.cnf").write_text(
            Templates.mariadb_cnf()
        )

    # ----- step 5: write_traefik_conf ---------------------------------------

    def write_traefik_conf(self) -> None:
        cfg_dir = self.cfg.barista_home / "config" / "traefik"
        (cfg_dir / "traefik.yml").write_text(
            Templates.traefik_yml(self.cfg.network, self.cfg.email, self.cfg.domain)
        )
        # empty dynamic.yml; Barista rewrites it as sites change
        (cfg_dir / "dynamic.yml").touch()

    # ----- step 6: stage_docker_manager -------------------------------------

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

    # ----- step 7: write_compose --------------------------------------------

    def write_compose(self) -> None:
        self.cfg.compose_file.write_text(
            Templates.compose_yml(
                home=str(self.cfg.barista_home),
                network=self.cfg.network,
                no_traefik=self.cfg.no_traefik,
            )
        )

    # ----- step 8: compose_up -----------------------------------------------

    def compose_up(self) -> None:
        if not self.docker.network_exists(self.cfg.network):
            self.docker.run(["docker", "network", "create", self.cfg.network])

        compose = self._compose_prefix()
        self.docker.run([*compose, "build", "docker-manager"])
        self.docker.run([*compose, "pull", "--ignore-pull-failures"], check=False)
        self.docker.run([*compose, "up", "-d"])

        self._wait_mariadb()
        self._wait_docker_manager()

    def _compose_prefix(self) -> list[str]:
        return [
            "docker", "compose",
            "--project-directory", str(self.cfg.barista_home),
            "--env-file", str(self.cfg.env_file),
        ]

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
        env = parse_env_file(self.cfg.env_file)
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

    # ----- step 9: bootstrap_cp ---------------------------------------------

    def bootstrap_cp(self) -> None:
        """Create the control-plane bench. Delegates to `Bench`."""
        self.bench.bootstrap()

    # ----- summary / lifecycle ---------------------------------------------

    def print_summary(self) -> None:
        env = parse_env_file(self.cfg.env_file)
        domain = env.get("BARISTA_DOMAIN", self.cfg.domain)
        scheme = "https" if (self.cfg.email and not domain.endswith(".localhost")) else "http"
        url = f"{scheme}://{domain}/barista"
        admin = env.get("BARISTA_ADMIN_PASSWORD", "(see ~/.barista/.env)")
        print(
            f"\n{self.log.c['BOLD']}Barista is ready ☕{self.log.c['RST']}\n\n"
            f"  URL:        {self.log.c['BOLD']}{url}{self.log.c['RST']}\n"
            f"  Username:   Administrator\n"
            f"  Password:   {admin}\n\n"
            f"  Bench:      {self.bench.name}   (running)\n"
            f"  Site:       {domain}                  (control-plane)\n"
            f"  Data dir:   {self.cfg.barista_home}\n\n"
            f"  {self.log.c['DIM']}Re-run this script any time — it is idempotent.{self.log.c['RST']}\n"
            f"  {self.log.c['DIM']}Uninstall:   {sys.argv[0]} --uninstall{self.log.c['RST']}\n"
            f"  {self.log.c['DIM']}Wipe data:   {sys.argv[0]} --purge{self.log.c['RST']}\n"
        )

    def uninstall(self) -> None:
        self.log.log("Stopping containers")
        self.docker.run([*self._compose_prefix(), "down"], check=False)
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
