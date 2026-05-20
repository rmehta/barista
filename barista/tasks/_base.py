"""Base class for every privileged task.

Each task is a small subclass: override `kind` and `run()`. The base
class handles status tracking, audit logging, error capture, and
realtime publishing. Subclasses stay short and readable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import frappe

from barista.dm_client import DockerManagerClient, get_client
from barista.exceptions import BaristaError


class BaristaTask(ABC):
    """One unit of privileged work.

    Subclasses define ``kind`` and implement ``run()``. The task
    framework wires up the corresponding Bench Action row, calls
    ``run()`` exactly once, and records the outcome.
    """

    kind: str  # human-readable action name, must match Bench Action.action

    def __init__(self, bench_action: str, **params: Any):
        self.action_name = bench_action
        self.action = frappe.get_doc("Bench Action", bench_action)
        self.params = params
        self._dm: DockerManagerClient | None = None

    @property
    def dm(self) -> DockerManagerClient:
        if self._dm is None:
            self._dm = get_client()
        return self._dm

    def execute(self) -> None:
        """Entrypoint called by the queue worker."""
        self.action.mark_running()
        try:
            self.run()
            self.action.mark_success()
        except BaristaError as e:
            self.action.mark_failure(error=str(e))
            frappe.log_error(title=f"barista.{self.kind}.failure", message=str(e))
        except Exception as e:  # noqa: BLE001 — anything else is a bug
            self.action.mark_failure(error=f"{type(e).__name__}: {e}")
            frappe.log_error(title=f"barista.{self.kind}.crash",
                              message=frappe.get_traceback())

    @abstractmethod
    def run(self) -> None:
        """Actual work. Subclasses must override."""


def enqueue_task(task_cls: type[BaristaTask], target_type: str, target: str,
                 action: str, **params: Any) -> str:
    """Create the Bench Action row + enqueue the task.

    Returns the Bench Action name so the API can hand it back to the
    UI for realtime subscription.
    """
    bench_action = frappe.get_doc({
        "doctype": "Bench Action",
        "target_type": target_type,
        "target": target,
        "action": action,
    }).insert(ignore_permissions=True)

    frappe.enqueue(
        "barista.tasks._base.run_task",
        queue="barista-agent",
        job_name=f"{task_cls.__name__}-{target}-{bench_action.name}",
        task_path=f"{task_cls.__module__}.{task_cls.__name__}",
        bench_action=bench_action.name,
        **params,
    )
    return bench_action.name


def run_task(task_path: str, bench_action: str, **params: Any) -> None:
    """Module-level shim Frappe's enqueue can resolve.

    We can't pickle the class itself across the queue, so we pass the
    dotted path and import it here.
    """
    module_path, _, cls_name = task_path.rpartition(".")
    task_cls = getattr(frappe.get_module(module_path), cls_name)
    task_cls(bench_action=bench_action, **params).execute()
