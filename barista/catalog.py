"""First-party Frappe app catalog.

The catalog is the list of apps Barista pre-seeds into `Bench App` so
new users see a familiar set of options the first time they open the
dashboard. Users can add their own with `add_custom_app`.

Treated as data: one tuple per app, no logic. Edit this list to add
or remove apps from the default install. `seed()` is idempotent and
re-runnable; existing rows are not overwritten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import frappe


@dataclass(frozen=True)
class CatalogApp:
    app_name: str
    title: str
    repository_url: str
    default_branch: str
    description: str

    def as_doc(self) -> dict:
        return {
            "doctype": "Bench App",
            "app_name": self.app_name,
            "title": self.title,
            "repository_url": self.repository_url,
            "default_branch": self.default_branch,
            "description": self.description,
            "is_private": 0,
        }


# Ordered most-to-least popular. `frappe` first because it's the
# precondition for everything else.
FIRST_PARTY: tuple[CatalogApp, ...] = (
    CatalogApp(
        app_name="frappe",
        title="Frappe Framework",
        repository_url="https://github.com/frappe/frappe",
        default_branch="version-15",
        description="The full-stack web application framework Barista runs on.",
    ),
    CatalogApp(
        app_name="erpnext",
        title="ERPNext",
        repository_url="https://github.com/frappe/erpnext",
        default_branch="version-15",
        description="Open-source ERP: accounting, stock, manufacturing, projects.",
    ),
    CatalogApp(
        app_name="hrms",
        title="Frappe HR",
        repository_url="https://github.com/frappe/hrms",
        default_branch="version-15",
        description="Payroll, attendance, leave, recruitment.",
    ),
    CatalogApp(
        app_name="crm",
        title="Frappe CRM",
        repository_url="https://github.com/frappe/crm",
        default_branch="main",
        description="Lead, deal, and contact management.",
    ),
    CatalogApp(
        app_name="insights",
        title="Frappe Insights",
        repository_url="https://github.com/frappe/insights",
        default_branch="main",
        description="Business analytics and dashboards on top of your data.",
    ),
    CatalogApp(
        app_name="builder",
        title="Frappe Builder",
        repository_url="https://github.com/frappe/builder",
        default_branch="main",
        description="Visual page builder for web pages.",
    ),
    CatalogApp(
        app_name="lms",
        title="Frappe LMS",
        repository_url="https://github.com/frappe/lms",
        default_branch="main",
        description="Learning management system: courses, batches, quizzes.",
    ),
    CatalogApp(
        app_name="helpdesk",
        title="Frappe Helpdesk",
        repository_url="https://github.com/frappe/helpdesk",
        default_branch="main",
        description="Ticketing and customer support.",
    ),
    CatalogApp(
        app_name="wiki",
        title="Frappe Wiki",
        repository_url="https://github.com/frappe/wiki",
        default_branch="master",
        description="Documentation and knowledge base.",
    ),
    CatalogApp(
        app_name="gameplan",
        title="Gameplan",
        repository_url="https://github.com/frappe/gameplan",
        default_branch="main",
        description="Team discussions, projects, and tasks.",
    ),
    CatalogApp(
        app_name="drive",
        title="Frappe Drive",
        repository_url="https://github.com/frappe/drive",
        default_branch="main",
        description="File sharing and document collaboration.",
    ),
    CatalogApp(
        app_name="print_designer",
        title="Print Designer",
        repository_url="https://github.com/frappe/print_designer",
        default_branch="main",
        description="Visual designer for print formats.",
    ),
)


# ---- seeding ----

def seed() -> int:
    """Insert any first-party rows that are missing. Returns count inserted.

    Idempotent. Does NOT overwrite rows the user has edited.
    """
    inserted = 0
    for app in FIRST_PARTY:
        if frappe.db.exists("Bench App", app.app_name):
            continue
        frappe.get_doc(app.as_doc()).insert(ignore_permissions=True)
        inserted += 1
    if inserted:
        frappe.db.commit()
    return inserted


# ---- custom-app helpers ----

# Conservative matcher: HTTPS or git@ URLs, optional .git suffix.
_GIT_URL_RX = re.compile(
    r"^(?:"
    r"https?://[\w.\-]+(?::\d+)?/[\w./\-]+?"        # https://host[:port]/owner/repo
    r"|git@[\w.\-]+:[\w./\-]+?"                       # git@host:owner/repo
    r")(?:\.git)?$"
)

_APP_NAME_RX = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def is_valid_git_url(url: str) -> bool:
    return bool(url) and bool(_GIT_URL_RX.match(url))


def derive_app_name(repository_url: str) -> str:
    """Derive a snake_case app name from a Git URL.

    `https://github.com/owner/my-cool-app(.git)` → `my_cool_app`
    """
    if not repository_url:
        raise ValueError("repository_url is required")
    tail = repository_url.rstrip("/").rsplit("/", 1)[-1]
    if tail.endswith(".git"):
        tail = tail[:-4]
    if ":" in tail:                # git@host:owner/repo case where rsplit didn't help
        tail = tail.rsplit(":", 1)[-1].rsplit("/", 1)[-1]
    name = tail.lower().replace("-", "_")
    if not _APP_NAME_RX.match(name):
        raise ValueError(
            f"could not derive a valid app name from {repository_url!r} "
            f"(got {name!r})"
        )
    return name
