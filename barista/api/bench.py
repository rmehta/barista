"""Whitelisted methods for bench-level actions.

Each method is a thin wrapper: it validates permissions, ensures the
target DocType exists, and enqueues the matching BaristaTask. The
heavy lifting lives in barista/tasks/.
"""

from __future__ import annotations

import frappe
from frappe import _

from ..permissions import require_admin
from ..tasks._base import enqueue_task
from ..tasks.bench import DestroyBench, RestartBench, StartBench, StopBench


def _ensure(bench: str) -> None:
    if not frappe.db.exists("Bench Host", bench):
        frappe.throw(_("Bench {0} does not exist").format(bench), frappe.DoesNotExistError)
    frappe.has_permission("Bench Host", "write", bench, throw=True)


@frappe.whitelist()
def start(bench: str) -> dict:
    require_admin()
    _ensure(bench)
    action = enqueue_task(StartBench, "Bench Host", bench, "Start")
    return {"bench_action": action}


@frappe.whitelist()
def stop(bench: str, timeout: int = 10) -> dict:
    require_admin()
    _ensure(bench)
    action = enqueue_task(StopBench, "Bench Host", bench, "Stop", timeout=int(timeout))
    return {"bench_action": action}


@frappe.whitelist()
def restart(bench: str) -> dict:
    require_admin()
    _ensure(bench)
    action = enqueue_task(RestartBench, "Bench Host", bench, "Restart")
    return {"bench_action": action}


@frappe.whitelist()
def destroy(bench: str, force: int = 0) -> dict:
    require_admin()
    _ensure(bench)
    action = enqueue_task(DestroyBench, "Bench Host", bench, "Destroy",
                           force=bool(int(force)))
    return {"bench_action": action}


@frappe.whitelist()
def stats(bench: str) -> dict:
    """Read-through to docker-manager. Cheap; doesn't enqueue."""
    require_admin()
    _ensure(bench)
    from ..dm_client import get_client
    return get_client().stats(bench)
