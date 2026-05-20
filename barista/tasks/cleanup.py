"""Daily cleanup tasks."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, now_datetime


def purge_old_snapshots() -> None:
    """Delete Site Backup rows older than retention; keep one a week."""
    settings = frappe.get_single("Barista Settings")
    days = settings.backup_retention_days or 14
    cutoff = add_days(now_datetime(), -days)
    rows = frappe.get_all("Site Backup",
        filters={"finished_at": ["<", cutoff], "status": "Success"},
        pluck="name")
    for name in rows:
        frappe.delete_doc("Site Backup", name, ignore_permissions=True,
                          delete_permanently=True)
