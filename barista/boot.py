"""Extend Frappe's boot info with Barista-specific data the SPA needs at load time."""

import frappe


def extend(bootinfo: dict) -> None:
    bootinfo["barista"] = {
        "version": frappe.get_attr("barista.__version__"),
        "roles": _user_barista_roles(),
        "docker_manager_url": frappe.conf.get("barista_docker_manager_url") or None,
    }


def _user_barista_roles() -> list[str]:
    user_roles = set(frappe.get_roles())
    return sorted(user_roles & {"Barista Admin", "Barista Editor", "Barista Viewer"})
