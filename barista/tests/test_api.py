"""Smoke tests for API methods.

We don't run the queued task here (it would call docker-manager); we
verify the API correctly inserts a Bench Action and returns its name.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from barista.api import bench as bench_api


class TestBenchAPI(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Bench Spec", "test-spec"):
            frappe.get_doc({
                "doctype": "Bench Spec",
                "spec_name": "test-spec",
                "is_system": 1,
            }).insert(ignore_permissions=True)
        if not frappe.db.exists("Bench Host", "api-bench"):
            frappe.get_doc({
                "doctype": "Bench Host",
                "bench_name": "api-bench",
                "spec": "test-spec",
                "status": "Running",
                "http_port": 18098,
            }).insert(ignore_permissions=True)

    def _as_admin(self):
        if not frappe.db.exists("User", "admin@barista.test"):
            user = frappe.get_doc({
                "doctype": "User",
                "email": "admin@barista.test",
                "first_name": "Test Admin",
                "send_welcome_email": 0,
                "roles": [{"role": "Barista Admin"}],
            }).insert(ignore_permissions=True)
        else:
            user = frappe.get_doc("User", "admin@barista.test")
        frappe.set_user(user.name)

    def test_restart_creates_bench_action(self):
        self._as_admin()
        out = bench_api.restart("api-bench")
        self.assertIn("bench_action", out)
        action = frappe.get_doc("Bench Action", out["bench_action"])
        self.assertEqual(action.target_type, "Bench Host")
        self.assertEqual(action.target, "api-bench")
        self.assertEqual(action.action, "Restart")
        self.assertEqual(action.status, "Queued")

    def test_restart_blocked_for_viewer(self):
        # ensure a Viewer user
        if not frappe.db.exists("User", "viewer@barista.test"):
            frappe.get_doc({
                "doctype": "User",
                "email": "viewer@barista.test",
                "first_name": "Test Viewer",
                "send_welcome_email": 0,
                "roles": [{"role": "Barista Viewer"}],
            }).insert(ignore_permissions=True)
        frappe.set_user("viewer@barista.test")

        with self.assertRaises(frappe.PermissionError):
            bench_api.restart("api-bench")
