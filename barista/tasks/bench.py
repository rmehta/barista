"""Bench lifecycle tasks. Every task is one short class."""

from __future__ import annotations

import frappe

from ._base import BaristaTask


def _update_status(bench: str, status: str) -> None:
    """Update Bench Host.status + publish realtime."""
    doc = frappe.get_doc("Bench Host", bench)
    doc.status = status
    doc.save(ignore_permissions=True)
    doc.publish_status()


class StartBench(BaristaTask):
    kind = "Start"

    def run(self) -> None:
        name = self.action.target
        self.dm.start_bench(name)
        _update_status(name, "Running")


class StopBench(BaristaTask):
    kind = "Stop"

    def run(self) -> None:
        name = self.action.target
        self.dm.stop_bench(name, timeout=self.params.get("timeout", 10))
        _update_status(name, "Stopped")


class RestartBench(BaristaTask):
    kind = "Restart"

    def run(self) -> None:
        name = self.action.target
        self.dm.restart_bench(name)
        _update_status(name, "Running")


class DestroyBench(BaristaTask):
    kind = "Destroy"

    def run(self) -> None:
        name = self.action.target
        bench = frappe.get_doc("Bench Host", name)
        bench.on_trash()  # raises if non-archived sites exist
        self.dm.destroy_bench(name, force=bool(self.params.get("force")))
        frappe.delete_doc("Bench Host", name, ignore_permissions=True,
                          delete_permanently=True)
