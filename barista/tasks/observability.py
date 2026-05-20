"""Periodic observability refresh tasks. Stubs in v0.1; the real
collectors live in specs/07-observability.md and will be implemented as a
follow-up."""

import frappe


def refresh_error_snapshots() -> None:
    """Walk every site, ask its API for error count last 24h.

    v0.1 implementation: no-op; we just touch the function so the
    scheduler config is valid. The proxy/API side will be wired in a
    later milestone.
    """
    if not frappe.db.exists("DocType", "Site"):
        return
    # placeholder — see specs/07-observability.md
