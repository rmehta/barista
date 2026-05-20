"""Whitelisted methods for managing the Bench App catalog.

The first-party catalog is seeded automatically. These endpoints let
users add their own private/third-party apps via a Git URL.
"""

from __future__ import annotations

import frappe
from frappe import _

from ..catalog import derive_app_name, is_valid_git_url
from ..permissions import require_admin


@frappe.whitelist()
def add_custom_app(repository_url: str,
                   default_branch: str = "main",
                   app_name: str | None = None,
                   title: str | None = None,
                   description: str | None = None,
                   is_private: int = 0,
                   ) -> dict:
    """Register a custom (non-first-party) app source by Git URL.

    Returns the Bench App row as a dict.
    """
    require_admin()
    repository_url = (repository_url or "").strip()
    if not is_valid_git_url(repository_url):
        frappe.throw(_("{0} is not a valid Git URL").format(repository_url))

    name = (app_name or derive_app_name(repository_url)).strip().lower()

    if frappe.db.exists("Bench App", name):
        frappe.throw(_("App {0} already exists in the catalog").format(name))

    doc = frappe.get_doc({
        "doctype": "Bench App",
        "app_name": name,
        "title": title or name.replace("_", " ").title(),
        "repository_url": repository_url,
        "default_branch": default_branch or "main",
        "description": description or "",
        "is_private": int(bool(int(is_private))),
    }).insert(ignore_permissions=False)

    return doc.as_dict()


@frappe.whitelist()
def list_apps() -> list[dict]:
    """Read-only list, sorted with first-party first."""
    rows = frappe.get_all(
        "Bench App",
        fields=["name", "app_name", "title", "repository_url",
                "default_branch", "is_private", "description"],
        order_by="app_name asc",
    )
    return [_annotate(r) for r in rows]


def _annotate(row: dict) -> dict:
    row = dict(row)
    row["is_first_party"] = bool(
        row.get("repository_url", "").startswith("https://github.com/frappe/")
    )
    return row
