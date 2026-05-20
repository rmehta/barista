"""The Barista installer.

Layout:

  installer/
  ├── __init__.py    # re-exports + version
  ├── __main__.py    # `python -m installer` entry point
  ├── constants.py   # tunable defaults + magic numbers
  ├── errors.py      # InstallerError
  ├── logger.py      # pretty terminal output
  ├── secrets.py     # random_hex
  ├── env_file.py    # read/write key=value files
  ├── docker.py      # thin `docker` CLI wrapper
  ├── runner.py      # StepRunner: ordered, marker-gated steps
  ├── config.py      # Config dataclass + argparse
  ├── templates.py   # config-file rendering (pure functions)
  ├── installer.py   # Installer class with one method per install step
  └── cli.py         # main() — wires everything together

Each file is small enough to read in one screen. The Installer class
is the biggest (~400 lines) because every step lives there as a
method, which makes them easy to test in isolation.
"""

from . import secrets  # noqa: F401 — exposed for monkeypatching in tests
from .cli import build_install_steps, main
from .config import Config
from .constants import (
    BENCH_INTERNAL_PORT,
    BENCH_RUNTIME_PATH,
    DEFAULTS_BASE_IMAGE,
    DEFAULTS_BRANCH,
    DEFAULTS_DOMAIN,
    DEFAULTS_NETWORK,
    DEFAULTS_PORT_START,
    DEFAULTS_REPO,
    __version__,
)
from .docker import Docker
from .env_file import parse_env_file
from .errors import InstallerError
from .installer import Installer
from .logger import Logger
from .runner import StepRunner
from .secrets import random_hex
from .templates import Templates

__all__ = [
    "BENCH_INTERNAL_PORT",
    "BENCH_RUNTIME_PATH",
    "Config",
    "DEFAULTS_BASE_IMAGE",
    "DEFAULTS_BRANCH",
    "DEFAULTS_DOMAIN",
    "DEFAULTS_NETWORK",
    "DEFAULTS_PORT_START",
    "DEFAULTS_REPO",
    "Docker",
    "Installer",
    "InstallerError",
    "Logger",
    "StepRunner",
    "Templates",
    "__version__",
    "build_install_steps",
    "main",
    "parse_env_file",
    "random_hex",
    "secrets",
]
