"""Install/uninstall hooks. The big one is `register_control_plane`
which is called by install.sh once, after the Barista app and site
have been created — it writes the rows that make Barista's dashboard
show itself as a managed bench."""

import frappe


def after_install() -> None:
    _ensure_roles()
    _ensure_settings()


def _ensure_roles() -> None:
    for role in ("Barista Admin", "Barista Editor", "Barista Viewer"):
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)


def _ensure_settings() -> None:
    if not frappe.db.exists("Barista Settings", "Barista Settings"):
        frappe.get_doc({"doctype": "Barista Settings"}).insert(ignore_permissions=True)


def register_control_plane() -> None:
    """Called by install.sh after the control-plane site exists.

    Writes a Bench Spec + Bench Host + Site row so the dashboard sees
    the bootstrap bench as a managed entity. Idempotent.
    """
    _ensure_roles()
    _ensure_settings()

    if not frappe.db.exists("Bench Spec", "barista-cp"):
        frappe.get_doc({
            "doctype": "Bench Spec",
            "spec_name": "barista-cp",
            "description": "Control-plane bench, created by install.sh",
            "python_version": "3.11",
            "node_version": "20",
            "frappe_branch": "version-15",
            "is_system": 1,
        }).insert(ignore_permissions=True)

    bench_name = "default"
    if not frappe.db.exists("Bench Host", bench_name):
        frappe.get_doc({
            "doctype": "Bench Host",
            "bench_name": bench_name,
            "spec": "barista-cp",
            "status": "Running",
            "http_port": frappe.conf.get("barista_http_port") or 18000,
            "host_path": frappe.conf.get("barista_host_path")
                or "/home/frappe/.barista/data/benches/default",
        }).insert(ignore_permissions=True)

    site_name = frappe.local.site
    if not frappe.db.exists("Site", site_name):
        frappe.get_doc({
            "doctype": "Site",
            "site_name": site_name,
            "bench": bench_name,
            "status": "Active",
            "is_control_plane": 1,
            "backup_schedule": "Daily",
        }).insert(ignore_permissions=True)

    frappe.db.commit()
