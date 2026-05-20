#!/usr/bin/env python3
"""Barista installer — bootstrap entry point.

Two ways this runs:

  1. From a git checkout:
       ./install.py [...flags...]
     The `installer/` package sits next to install.py, so we just
     `python -m installer` from this directory.

  2. From a one-liner:
       curl -fsSL https://raw.githubusercontent.com/rmehta/barista/main/install.py | python3 -
     `__file__` resolves to <stdin>, so we git-clone the repo to a
     temp dir and re-exec `python -m installer` from there.

Either path lands in `installer/cli.py:main`. Read that file (and
the rest of `installer/`) for the actual install logic — this file
is intentionally tiny.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = "https://github.com/rmehta/barista"
BRANCH = "main"


def _script_dir() -> Path | None:
    """Where install.py lives — or None if run from stdin (curl|python3)."""
    f = globals().get("__file__")
    if not f or f in ("<stdin>", "-"):
        return None
    try:
        path = Path(f).resolve()
    except OSError:
        return None
    return path.parent if path.is_file() else None


def _installer_root() -> Path:
    """Return a directory containing an `installer/` package."""
    here = _script_dir()
    if here and (here / "installer").is_dir():
        return here

    if shutil.which("git") is None:
        sys.exit("git is required when running install.py via curl|python3")

    tmp = Path(tempfile.mkdtemp(prefix="barista-installer-"))
    sys.stderr.write(f"==> Cloning {REPO} to {tmp}\n")
    subprocess.check_call([
        "git", "clone", "--depth", "1", "--branch", BRANCH, REPO, str(tmp),
    ])
    return tmp


def main() -> int:
    root = _installer_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(root) + os.pathsep + env.get("PYTHONPATH", "")
    ).rstrip(os.pathsep)
    return subprocess.call(
        [sys.executable, "-m", "installer", *sys.argv[1:]],
        cwd=str(root),
        env=env,
    )


if __name__ == "__main__":
    sys.exit(main())
