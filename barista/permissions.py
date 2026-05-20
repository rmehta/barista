"""Role gating for privileged actions.

`frappe.has_permission` covers DocType perms; this module adds the
extra "you must hold role X to call this action" check on top.
"""

import frappe
from frappe import _


def require_role(role: str) -> None:
    if role in frappe.get_roles():
        return
    if "System Manager" in frappe.get_roles():
        return
    frappe.throw(_("You need the {0} role to do that.").format(role),
                 frappe.PermissionError)


def require_admin() -> None:
    require_role("Barista Admin")


def require_editor() -> None:
    if any(r in frappe.get_roles() for r in ("Barista Admin", "Barista Editor", "System Manager")):
        return
    frappe.throw(_("You need the Barista Editor role to do that."),
                 frappe.PermissionError)
