import frappe
from frappe.tests.utils import FrappeTestCase


class TestSite(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Bench Spec", "test-spec"):
            frappe.get_doc({
                "doctype": "Bench Spec",
                "spec_name": "test-spec",
                "is_system": 1,
            }).insert(ignore_permissions=True)
        if not frappe.db.exists("Bench Host", "test-bench"):
            frappe.get_doc({
                "doctype": "Bench Host",
                "bench_name": "test-bench",
                "spec": "test-spec",
                "status": "Running",
                "http_port": 18099,
            }).insert(ignore_permissions=True)

    def test_create_site_derives_db_name(self):
        site = frappe.get_doc({
            "doctype": "Site",
            "site_name": "shop.localhost",
            "bench": "test-bench",
            "status": "Active",
        }).insert(ignore_permissions=True)
        self.assertTrue(site.db_name.startswith("_"))
        self.assertEqual(len(site.db_name), 16)
        self.assertTrue(site.service_token)

    def test_invalid_site_name_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({
                "doctype": "Site",
                "site_name": "Has Spaces",
                "bench": "test-bench",
            }).insert(ignore_permissions=True)

    def test_digit_leading_nip_io_name_accepted(self):
        """`<ip>.nip.io` is the default control-plane domain when a
        public IP is detected at install time — it starts with a
        digit, which the validator must not reject (RFC 1123 allows
        digit-leading hostname labels)."""
        site = frappe.get_doc({
            "doctype": "Site",
            "site_name": "64.227.182.89.nip.io",
            "bench": "test-bench",
            "status": "Active",
        }).insert(ignore_permissions=True)
        self.assertTrue(site.db_name.startswith("_"))

    def test_control_plane_cannot_be_deleted(self):
        cp = frappe.get_doc({
            "doctype": "Site",
            "site_name": "cp.localhost",
            "bench": "test-bench",
            "status": "Active",
            "is_control_plane": 1,
        }).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            cp.delete()
