"""Frappe-runner tests for the Bench Host DocType.

These run under `bench --site test_site run-tests --app barista`. They
assume the standard Frappe FrappeTestCase contract: each test runs in
a DB transaction that is rolled back at the end.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from barista.exceptions import BenchInUseError


class TestBenchHost(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Bench Spec", "test-spec"):
            spec = frappe.get_doc({
                "doctype": "Bench Spec",
                "spec_name": "test-spec",
                "is_system": 1,
            })
            spec.insert(ignore_permissions=True)

    def _new_host(self, name: str = "test-bench"):
        return frappe.get_doc({
            "doctype": "Bench Host",
            "bench_name": name,
            "spec": "test-spec",
            "status": "Pending",
            "http_port": 18001,
        }).insert(ignore_permissions=True)

    def test_create_simple(self):
        host = self._new_host("simple-bench")
        self.assertEqual(host.status, "Pending")
        self.assertTrue(host.created_on)

    def test_invalid_name_rejected(self):
        for bad in ("Bad Name", "1leading", "", "TOO-LONG-" + "x" * 40):
            with self.assertRaises(frappe.ValidationError):
                frappe.get_doc({
                    "doctype": "Bench Host",
                    "bench_name": bad,
                    "spec": "test-spec",
                }).insert(ignore_permissions=True)

    def test_destroy_blocked_when_site_active(self):
        host = self._new_host("busy-bench")
        frappe.get_doc({
            "doctype": "Site",
            "site_name": "busy.localhost",
            "bench": host.name,
            "status": "Active",
        }).insert(ignore_permissions=True)
        with self.assertRaises(BenchInUseError):
            host.on_trash()
