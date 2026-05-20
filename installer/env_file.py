"""Read shell-style `KEY=VALUE` files (~/.barista/.env, etc.).

We don't use python-dotenv (avoiding deps); the format is simple
enough to handle ourselves. Comments (`#`) and blank lines skipped.
"""

from __future__ import annotations

from pathlib import Path


def parse_env_file(path: Path) -> dict[str, str]:
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
