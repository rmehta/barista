"""Dashboard aggregate endpoints — small, read-only helpers the SPA
calls to fill the home page."""

import frappe


@frappe.whitelist()
def overview() -> dict:
    """Counts for the home cards."""
    return {
        "benches": {
            "running": frappe.db.count("Bench Host", {"status": "Running"}),
            "stopped": frappe.db.count("Bench Host", {"status": "Stopped"}),
            "errored": frappe.db.count("Bench Host", {"status": "Errored"}),
        },
        "sites": {
            "active": frappe.db.count("Site", {"status": "Active"}),
            "broken": frappe.db.count("Site", {"status": "Broken"}),
            "archived": frappe.db.count("Site", {"status": "Archived"}),
        },
        "actions_last_hour": _actions_last_hour(),
    }


def _actions_last_hour() -> dict:
    from frappe.utils import add_to_date, now_datetime
    since = add_to_date(now_datetime(), hours=-1)
    by_status = frappe.db.sql(
        """SELECT status, COUNT(*) AS n FROM `tabBench Action`
           WHERE triggered_at >= %s
           GROUP BY status""",
        (since,), as_dict=True,
    )
    return {row.status.lower(): row.n for row in by_status}
