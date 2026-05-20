"""CLI flags + computed paths.

`Config` is the immutable bundle every other component reads. Built
once from `sys.argv` by `Config.from_argv` and threaded through.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from pathlib import Path

from .constants import (
    DEFAULTS_BASE_IMAGE,
    DEFAULTS_BRANCH,
    DEFAULTS_DOMAIN,
    DEFAULTS_NETWORK,
    DEFAULTS_PORT_START,
    DEFAULTS_REPO,
)


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
    # Where install.py lives. In curl|python3 mode this is the cloned
    # repo dir; in a checkout it's the repo root.
    script_dir: Path = field(default_factory=lambda: Path.cwd())

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
        args = _build_parser().parse_args(argv)
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


def _build_parser() -> argparse.ArgumentParser:
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
    return p
