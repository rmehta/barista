"""Site lifecycle tasks. Each task runs `bench` commands inside the
target bench container via docker-manager's exec endpoint."""

from __future__ import annotations

import frappe

from ._base import BaristaTask


class CreateSite(BaristaTask):
    kind = "Create"

    def run(self) -> None:
        site = self.action.target
        doc = frappe.get_doc("Site", site)
        admin_password = self.params["admin_password"]
        apps = self.params.get("apps") or []

        cmd = [
            "bench", "new-site",
            "--no-mariadb-socket",
            "--admin-password", admin_password,
            "--mariadb-root-password", self.params["mariadb_root_password"],
        ]
        for app in apps:
            cmd += ["--install-app", app]
        cmd.append(site)

        self._run_in_bench(doc.bench, cmd, timeout_s=900)

        doc.status = "Active"
        doc.save(ignore_permissions=True)
        doc.publish_status()


class ArchiveSite(BaristaTask):
    kind = "Destroy"

    def run(self) -> None:
        site = self.action.target
        doc = frappe.get_doc("Site", site)
        self._run_in_bench(doc.bench, ["bench", "drop-site", "--force", site],
                            timeout_s=300)
        doc.status = "Archived"
        doc.save(ignore_permissions=True)
        doc.publish_status()


class MigrateSite(BaristaTask):
    kind = "Migrate"

    def run(self) -> None:
        site = self.action.target
        doc = frappe.get_doc("Site", site)
        doc.status = "Migrating"
        doc.save(ignore_permissions=True)
        doc.publish_status()
        self._run_in_bench(doc.bench, ["bench", "--site", site, "migrate"],
                            timeout_s=1800)
        doc.status = "Active"
        doc.save(ignore_permissions=True)
        doc.publish_status()


class InstallAppOnSite(BaristaTask):
    kind = "Install App"

    def run(self) -> None:
        site = self.action.target
        app = self.params["app"]
        doc = frappe.get_doc("Site", site)
        self._run_in_bench(
            doc.bench,
            ["bench", "--site", site, "install-app", app],
            timeout_s=900,
        )


class UninstallAppFromSite(BaristaTask):
    kind = "Uninstall App"

    def run(self) -> None:
        site = self.action.target
        app = self.params["app"]
        doc = frappe.get_doc("Site", site)
        self._run_in_bench(
            doc.bench,
            ["bench", "--site", site, "uninstall-app", app, "--yes"],
            timeout_s=600,
        )


# ---- helper attached to BaristaTask for site/backup tasks ---------------

def _run_in_bench(self: BaristaTask, bench: str, cmd: list[str],
                  timeout_s: int = 600) -> None:
    """Submit an exec to docker-manager, poll until done, copy log
    into the Bench Action row."""
    started = self.dm.exec_oneshot(bench, cmd, timeout_s=timeout_s)
    exec_id = started["exec_id"]
    self._wait_for_exec(bench, exec_id)


def _wait_for_exec(self: BaristaTask, bench: str, exec_id: str) -> None:
    import time

    offset = 0
    while True:
        chunk = self.dm.exec_log(bench, exec_id, since=offset)
        if chunk.get("data"):
            self.action.append_log(chunk["data"])
            offset = chunk["offset"]
        if chunk.get("status") in ("success", "failure", "cancelled"):
            if chunk["status"] == "failure":
                from barista.exceptions import DockerManagerError
                raise DockerManagerError(
                    f"exec failed in bench {bench}: {chunk.get('error')}"
                )
            return
        time.sleep(2)


# attach helpers as bound methods on the base task class
BaristaTask._run_in_bench = _run_in_bench  # type: ignore[attr-defined]
BaristaTask._wait_for_exec = _wait_for_exec  # type: ignore[attr-defined]
