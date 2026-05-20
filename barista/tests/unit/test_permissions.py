"""Role gating helpers."""

import frappe
import pytest

from barista.permissions import require_admin, require_editor


def test_require_admin_passes_for_admin(monkeypatch):
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Barista Admin"])
    require_admin()


def test_require_admin_passes_for_system_manager(monkeypatch):
    monkeypatch.setattr(frappe, "get_roles", lambda: ["System Manager"])
    require_admin()


def test_require_admin_blocks_viewer(monkeypatch):
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Barista Viewer"])
    with pytest.raises(frappe.PermissionError):
        require_admin()


def test_require_editor_allows_admin_and_editor(monkeypatch):
    for role in ("Barista Admin", "Barista Editor", "System Manager"):
        monkeypatch.setattr(frappe, "get_roles", lambda r=role: [r])
        require_editor()


def test_require_editor_blocks_viewer(monkeypatch):
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Barista Viewer"])
    with pytest.raises(frappe.PermissionError):
        require_editor()
