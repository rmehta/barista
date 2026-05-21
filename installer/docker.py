"""Thin wrapper around the `docker` CLI.

We shell out instead of using the Docker SDK so install.py stays
stdlib-only (so `curl ... | python3 -` Just Works).
"""

from __future__ import annotations

import shutil
import subprocess

from .utils import Logger


class Docker:
    """Methods come in two flavours:

    - `run(argv, ...)` — execute via `subprocess.run`. The single
      mockable seam in tests; honours dry-run.
    - Queries (`daemon_up`, `network_exists`, ...) — always live;
      they answer truthfully even in dry-run mode so the planning
      logic stays correct.
    """

    def __init__(self, logger: Logger, dry_run: bool = False):
        self.log = logger
        self.dry_run = dry_run

    def run(self, argv: list[str], capture: bool = False,
            check: bool = True, timeout: int | None = None,
            stdin: str | None = None) -> subprocess.CompletedProcess:
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

    # ---- queries ----

    def installed(self) -> bool:
        return shutil.which("docker") is not None

    def daemon_up(self) -> bool:
        try:
            return subprocess.run(
                ["docker", "info"], capture_output=True, check=False
            ).returncode == 0
        except FileNotFoundError:
            return False

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
