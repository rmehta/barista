"""The Barista installer.

Layout:

  installer/
  ├── __init__.py    # re-exports + version
  ├── constants.py   # tunable defaults + magic numbers
  ├── utils.py       # InstallerError, Logger, random_hex, parse_env_file
  ├── docker.py      # thin `docker` CLI wrapper
  ├── runner.py      # StepRunner: ordered, marker-gated steps
  ├── config.py      # Config dataclass + argparse
  ├── templates.py   # config-file rendering (pure functions)
  ├── bench.py       # Bench class: the control-plane bench container
  ├── installer.py   # Installer class: one method per install step
  └── cli.py         # main() — wires everything together; also the
                     #          `python -m installer.cli` entry point

Each file fits on a screen-and-a-half except installer.py and
bench.py (which hold one method per install sub-step — splitting
them further would just hide the install sequence).
"""

from . import utils  # noqa: F401 — exposed for monkeypatching in tests
from .bench import Bench
from .config import Config
from .constants import (
    BENCH_CONTAINER_NAME,
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
from .installer import Installer
from .runner import StepRunner
from .templates import Templates
from .utils import InstallerError, Logger, parse_env_file, random_hex

__all__ = [
    "BENCH_CONTAINER_NAME",
    "BENCH_INTERNAL_PORT",
    "BENCH_RUNTIME_PATH",
    "Bench",
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
    "parse_env_file",
    "random_hex",
    "utils",
]
