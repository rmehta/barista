"""Frappe-runner tests for the app catalog: seeding + custom-app API."""

import frappe
from frappe.tests.utils import FrappeTestCase

from barista import catalog
from barista.api import apps as apps_api


class TestCatalogSeeding(FrappeTestCase):
    def test_seed_creates_first_party_apps(self):
        # `bench --site test_site install-app barista` already ran
        # `after_install` (which calls seed). Verify the rows are
        # there.
        for app in catalog.FIRST_PARTY:
            self.assertTrue(
                frappe.db.exists("Bench App", app.app_name),
                f"missing catalog app: {app.app_name}",
            )

    def test_seed_is_idempotent(self):
        before = frappe.db.count("Bench App")
        catalog.seed()
        after = frappe.db.count("Bench App")
        self.assertEqual(before, after, "seed() should not insert duplicates")

    def test_seed_does_not_overwrite_edits(self):
        # User edits the title — seed must leave it alone.
        doc = frappe.get_doc("Bench App", "erpnext")
        doc.title = "MY EDITED TITLE"
        doc.save(ignore_permissions=True)
        catalog.seed()
        self.assertEqual(
            frappe.db.get_value("Bench App", "erpnext", "title"),
            "MY EDITED TITLE",
        )


class TestAddCustomApp(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("User", "admin@catalog.test"):
            frappe.get_doc({
                "doctype": "User",
                "email": "admin@catalog.test",
                "first_name": "Catalog Admin",
                "send_welcome_email": 0,
                "roles": [{"role": "Barista Admin"}],
            }).insert(ignore_permissions=True)

    def setUp(self):
        frappe.set_user("admin@catalog.test")
        # remove any stale custom apps from previous runs
        for stale in ("private_app", "my_cool_app"):
            if frappe.db.exists("Bench App", stale):
                frappe.delete_doc("Bench App", stale,
                                  ignore_permissions=True,
                                  delete_permanently=True)

    def test_add_custom_app_derives_name(self):
        out = apps_api.add_custom_app(
            repository_url="https://github.com/myorg/my-cool-app",
        )
        self.assertEqual(out["app_name"], "my_cool_app")
        self.assertEqual(out["default_branch"], "main")
        self.assertTrue(frappe.db.exists("Bench App", "my_cool_app"))

    def test_add_custom_app_rejects_bad_url(self):
        with self.assertRaises(frappe.ValidationError):
            apps_api.add_custom_app(repository_url="not a url")

    def test_add_custom_app_rejects_duplicate(self):
        # erpnext is in the seeded catalog
        with self.assertRaises(frappe.ValidationError):
            apps_api.add_custom_app(
                repository_url="https://github.com/frappe/erpnext",
                app_name="erpnext",
            )

    def test_add_custom_app_explicit_name(self):
        out = apps_api.add_custom_app(
            repository_url="https://github.com/myorg/private",
            app_name="private_app",
            is_private=1,
        )
        self.assertEqual(out["app_name"], "private_app")
        self.assertTrue(out["is_private"])

    def test_add_custom_app_blocked_for_viewer(self):
        if not frappe.db.exists("User", "viewer@catalog.test"):
            frappe.get_doc({
                "doctype": "User",
                "email": "viewer@catalog.test",
                "first_name": "Catalog Viewer",
                "send_welcome_email": 0,
                "roles": [{"role": "Barista Viewer"}],
            }).insert(ignore_permissions=True)
        frappe.set_user("viewer@catalog.test")
        with self.assertRaises(frappe.PermissionError):
            apps_api.add_custom_app(
                repository_url="https://github.com/x/y",
            )


class TestListApps(FrappeTestCase):
    def test_list_includes_first_party_flag(self):
        rows = apps_api.list_apps()
        self.assertTrue(rows)
        erp = next((r for r in rows if r["app_name"] == "erpnext"), None)
        self.assertIsNotNone(erp)
        self.assertTrue(erp["is_first_party"])
