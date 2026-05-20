"""Whitelisted methods for site-level actions."""

from __future__ import annotations

import frappe
from frappe import _

from ..permissions import require_editor
from ..tasks._base import enqueue_task
from ..tasks.backup import BackupSite
from ..tasks.site import (
    ArchiveSite,
    CreateSite,
    InstallAppOnSite,
    MigrateSite,
    UninstallAppFromSite,
)


def _ensure_site(site: str) -> None:
    if not frappe.db.exists("Site", site):
        frappe.throw(_("Site {0} does not exist").format(site), frappe.DoesNotExistError)
    frappe.has_permission("Site", "write", site, throw=True)


def _ensure_bench(bench: str) -> None:
    if not frappe.db.exists("Bench Host", bench):
        frappe.throw(_("Bench {0} does not exist").format(bench), frappe.DoesNotExistError)


@frappe.whitelist()
def create(bench: str, site_name: str, admin_password: str,
           mariadb_root_password: str, apps: list | None = None) -> dict:
    require_editor()
    _ensure_bench(bench)

    site_doc = frappe.get_doc({
        "doctype": "Site",
        "site_name": site_name,
        "bench": bench,
        "status": "Pending",
    }).insert(ignore_permissions=False)

    action = enqueue_task(
        CreateSite, "Site", site_doc.name, "Create",
        admin_password=admin_password,
        mariadb_root_password=mariadb_root_password,
        apps=apps or [],
    )
    return {"bench_action": action, "site": site_doc.name}


@frappe.whitelist()
def archive(site: str) -> dict:
    require_editor()
    _ensure_site(site)
    action = enqueue_task(ArchiveSite, "Site", site, "Destroy")
    return {"bench_action": action}


@frappe.whitelist()
def migrate(site: str) -> dict:
    require_editor()
    _ensure_site(site)
    action = enqueue_task(MigrateSite, "Site", site, "Migrate")
    return {"bench_action": action}


@frappe.whitelist()
def install_app(site: str, app: str) -> dict:
    require_editor()
    _ensure_site(site)
    action = enqueue_task(InstallAppOnSite, "Site", site, "Install App",
                           app=app)
    return {"bench_action": action}


@frappe.whitelist()
def uninstall_app(site: str, app: str) -> dict:
    require_editor()
    _ensure_site(site)
    action = enqueue_task(UninstallAppFromSite, "Site", site, "Uninstall App",
                           app=app)
    return {"bench_action": action}


@frappe.whitelist()
def backup(site: str, with_files: int = 1) -> dict:
    require_editor()
    _ensure_site(site)
    action = enqueue_task(BackupSite, "Site", site, "Backup",
                           with_files=bool(int(with_files)),
                           type="Manual")
    return {"bench_action": action}
