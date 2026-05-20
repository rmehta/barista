"""`main()` — entry point used by `python -m installer` and install.py.

Wires Config + Logger + Installer + StepRunner together. Holds the
list of steps that defines an install run.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from .config import Config
from .errors import InstallerError
from .installer import Installer
from .logger import Logger
from .runner import StepRunner


def build_install_steps(installer: Installer) -> list[tuple[str, Callable[[], None]]]:
    """The ordered install run. Centralised so the StepRunner can
    iterate it and tests can assert ordering stability."""
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
