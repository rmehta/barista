"""Leaf utilities used across the installer.

Originally one file each (`errors.py`, `secrets.py`, `env_file.py`,
`logger.py`); rolled together because each was under 50 lines and
splitting them just added imports without making anything clearer.

Contents:

  - `InstallerError`         — the only exception we raise
  - `random_hex(nbytes)`      — wrapper around stdlib token_hex
  - `parse_env_file(path)`    — read `KEY=VALUE` shell files
  - `detect_public_ip()`      — best-effort public IPv4 lookup
  - `Logger`                  — coloured terminal output
"""

from __future__ import annotations

import secrets as _stdlib_secrets
import sys
import urllib.request
from pathlib import Path

# ============================================================================
# Errors
# ============================================================================

class InstallerError(Exception):
    """Anything we can't recover from. main() catches it and exits 1."""


# ============================================================================
# Secrets
# ============================================================================

def random_hex(nbytes: int = 16) -> str:
    """Return `2 * nbytes` hex characters of cryptographic randomness."""
    return _stdlib_secrets.token_hex(nbytes)


# ============================================================================
# env file
# ============================================================================

def parse_env_file(path: Path) -> dict[str, str]:
    """Read a shell-style `KEY=VALUE` file (~/.barista/.env etc.).

    No deps. Comments (`#`) and blank lines are skipped.
    """
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


# ============================================================================
# Public-IP detection (for the default <ip>.nip.io domain)
# ============================================================================

# Endpoints that return the caller's public IPv4 as plain text. We
# query them at install time so the default domain becomes
# `<public-ip>.nip.io`, which resolves back to the same IP from
# anywhere — making the install web-accessible without DNS setup.
# Fail closed (return None) if none answer; the caller falls back to
# `barista.localhost`.
_PUBLIC_IP_ENDPOINTS = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
)


def detect_public_ip(timeout: float = 2.0) -> str | None:
    """Best-effort public IPv4 lookup. Returns None on any failure
    (offline, blocked, RFC 1918 / loopback response)."""
    for url in _PUBLIC_IP_ENDPOINTS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "barista-installer"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ip = r.read().decode("ascii", errors="replace").strip()
        except Exception:
            continue
        if _looks_like_public_ipv4(ip):
            return ip
    return None


def _looks_like_public_ipv4(s: str) -> bool:
    parts = s.split(".")
    if len(parts) != 4:
        return False
    try:
        a, b, _c, _d = (int(p) for p in parts)
    except ValueError:
        return False
    if not all(0 <= int(p) <= 255 for p in parts):
        return False
    # Reject the obvious non-public ranges. A returned RFC 1918 means
    # we're behind NAT with no real public IP visible — better to
    # fall back to localhost than mint a nip.io URL that can't reach us.
    if a == 10 or a == 127:
        return False
    if a == 169 and b == 254:
        return False
    if a == 172 and 16 <= b <= 31:
        return False
    if a == 192 and b == 168:
        return False
    return True


# ============================================================================
# Logger
# ============================================================================

class Logger:
    """Pretty terminal output with `==>`, `✓`, `⚠`, `✗` markers.

    Falls back to plain text when stdout is not a tty (CI, pipes).
    """

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
