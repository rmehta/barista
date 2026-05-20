"""Backup tasks."""

from __future__ import annotations

import frappe

from ._base import BaristaTask


class BackupSite(BaristaTask):
    kind = "Backup"

    def run(self) -> None:
        site = self.action.target
        with_files = bool(self.params.get("with_files", True))

        backup = frappe.get_doc({
            "doctype": "Site Backup",
            "site": site,
            "type": self.params.get("type", "Manual"),
            "with_files": with_files,
            "status": "Running",
        }).insert(ignore_permissions=True)

        try:
            site_doc = frappe.get_doc("Site", site)
            cmd = ["bench", "--site", site, "backup"]
            if with_files:
                cmd += ["--with-files"]
            self._run_in_bench(site_doc.bench, cmd, timeout_s=1800)
            # in a real install the backup task would parse `bench backup`'s
            # output for the file paths and size; here we keep it minimal
            backup.mark_done(path=f"/backups/{site}/", size_mb=0)
        except Exception:
            backup.mark_failed()
            raise


def run_scheduled_backups() -> None:
    """Scheduler-event entrypoint."""
    from ._base import enqueue_task

    sites = frappe.get_all("Site",
        filters={"backup_schedule": ["in", ("Daily", "Weekly")],
                 "status": "Active"},
        fields=["name", "backup_schedule"])
    for site in sites:
        if site.backup_schedule == "Weekly" and frappe.utils.now_datetime().weekday() != 0:
            continue
        enqueue_task(BackupSite, target_type="Site", target=site.name,
                     action="Backup", with_files=True, type="Scheduled")
