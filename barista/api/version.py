import frappe


@frappe.whitelist(allow_guest=False)
def info() -> dict:
    """Surface basic env info to the SPA on boot."""
    return {
        "version": frappe.get_attr("barista.__version__"),
        "frappe_version": frappe.__version__,
        "site": frappe.local.site,
        "user": frappe.session.user,
    }
