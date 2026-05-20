from . import __version__ as app_version  # noqa: F401

app_name = "barista"
app_title = "Barista"
app_publisher = "Frappe Technologies Pvt. Ltd."
app_description = "Manage local Frappe benches and sites via a Frappe-UI dashboard"
app_email = "developers@frappe.io"
app_license = "GNU Affero General Public License v3.0"

# SPA — mount /barista/* to the Vue app served from www/barista.html
website_route_rules = [
    {"from_route": "/barista/<path:app_path>", "to_route": "barista"},
]

# Boot info for the SPA
extend_bootinfo = "barista.boot.extend"

# Roles seeded on install
fixtures = [
    {
        "dt": "Role",
        "filters": [
            ["name", "in", ["Barista Admin", "Barista Editor", "Barista Viewer"]]
        ],
    },
]

# Scheduled tasks
scheduler_events = {
    "cron": {
        # every 15 seconds is too aggressive for the standard scheduler;
        # bench polling lives in the agent worker (see tasks.poll).
        "*/10 * * * *": [
            "barista.tasks.observability.refresh_error_snapshots",
        ],
        "0 2 * * *": [
            "barista.tasks.backup.run_scheduled_backups",
            "barista.tasks.cleanup.purge_old_snapshots",
        ],
    }
}

# Custom worker queues — install.sh wires barista-agent into the
# supervisord config so only it has the manager token.
queues = ["barista-agent"]
