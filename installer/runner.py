"""Ordered step runner with marker-file idempotency.

Each step is a `(name, callable)`. On success the runner writes
`<state_dir>/<name>.done`; subsequent runs skip that step.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .logger import Logger


class StepRunner:
    def __init__(self, state_dir: Path, logger: Logger, dry_run: bool = False):
        self.state_dir = state_dir
        self.log = logger
        self.dry_run = dry_run
        self._steps: list[tuple[str, Callable[[], None]]] = []

    def add(self, name: str, fn: Callable[[], None]) -> None:
        self._steps.append((name, fn))

    def marker(self, name: str) -> Path:
        return self.state_dir / f"{name}.done"

    def is_done(self, name: str) -> bool:
        return self.marker(name).exists()

    def run(self) -> None:
        for name, fn in self._steps:
            if self.is_done(name):
                self.log.ok(f"{name} (already done)")
                continue
            self.log.log(name)
            try:
                fn()
            except Exception as e:
                self.log.err(f"{name} failed: {e}")
                raise
            if not self.dry_run:
                self.state_dir.mkdir(parents=True, exist_ok=True)
                self.marker(name).touch()
            self.log.ok(name)
