"""Pretty terminal output. Stateless except for an isatty flag."""

from __future__ import annotations

import sys


class Logger:
    """Coloured log with `==>`, `✓`, `⚠`, `✗` markers.

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
