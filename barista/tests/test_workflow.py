"""End-to-end workflow test: create a site, install an app, log in.

The privileged tasks (which would call docker-manager) are stubbed so
we exercise the API layer + Bench Action lifecycle without needing a
real Docker daemon. The login portion uses Frappe's own auth on the
test site, which is the layer we actually control.
"""

from unittest.mock import patch

import frappe
from frappe.auth import LoginManager
from frappe.tests.utils import FrappeTestCase

from barista.api import bench as bench_api
from barista.api import site as site_api


class TestSiteLifecycle(FrappeTestCase):
    BENCH = "wf-bench"
    SPEC = "wf-spec"
    SITE = "shop.wf.localhost"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._ensure_spec()
        cls._ensure_bench()
        cls._ensure_admin_user()

    @classmethod
    def _ensure_spec(cls):
        if not frappe.db.exists("Bench Spec", cls.SPEC):
            frappe.get_doc({
                "doctype": "Bench Spec",
                "spec_name": cls.SPEC,
                "is_system": 1,
            }).insert(ignore_permissions=True)

    @classmethod
    def _ensure_bench(cls):
        if not frappe.db.exists("Bench Host", cls.BENCH):
            frappe.get_doc({
                "doctype": "Bench Host",
                "bench_name": cls.BENCH,
                "spec": cls.SPEC,
                "status": "Running",
                "http_port": 18097,
            }).insert(ignore_permissions=True)

    @classmethod
    def _ensure_admin_user(cls):
        if not frappe.db.exists("User", "wf-admin@barista.test"):
            frappe.get_doc({
                "doctype": "User",
                "email": "wf-admin@barista.test",
                "first_name": "WF Admin",
                "new_password": "wf-test-password-12345",
                "send_welcome_email": 0,
                "roles": [{"role": "Barista Admin"},
                          {"role": "Barista Editor"}],
            }).insert(ignore_permissions=True)

    def setUp(self):
        frappe.set_user("wf-admin@barista.test")
        # clean any leftover site row
        if frappe.db.exists("Site", self.SITE):
            doc = frappe.get_doc("Site", self.SITE)
            doc.flags.ignore_permissions = True
            frappe.delete_doc("Site", self.SITE,
                              ignore_permissions=True,
                              delete_permanently=True)

    # ---- 1. create a site ---------------------------------------------

    def test_create_site_inserts_row_and_action(self):
        out = site_api.create(
            bench=self.BENCH,
            site_name=self.SITE,
            admin_password="site-admin-pw-67890",
            mariadb_root_password="mariadb-root-pw",
            apps=["erpnext"],
        )
        self.assertIn("bench_action", out)
        self.assertEqual(out["site"], self.SITE)

        site = frappe.get_doc("Site", self.SITE)
        self.assertEqual(site.status, "Pending")
        self.assertEqual(site.bench, self.BENCH)
        self.assertTrue(site.db_name.startswith("_"))
        self.assertTrue(site.service_token)

        action = frappe.get_doc("Bench Action", out["bench_action"])
        self.assertEqual(action.target_type, "Site")
        self.assertEqual(action.action, "Create")
        self.assertEqual(action.status, "Queued")

    # ---- 2. install an app on a site ----------------------------------

    def test_install_app_creates_bench_action(self):
        # site must exist first
        site_api.create(
            bench=self.BENCH,
            site_name=self.SITE,
            admin_password="x",
            mariadb_root_password="y",
        )
        out = site_api.install_app(site=self.SITE, app="hrms")
        action = frappe.get_doc("Bench Action", out["bench_action"])
        self.assertEqual(action.action, "Install App")
        self.assertEqual(action.target, self.SITE)
        self.assertEqual(action.status, "Queued")

    def test_install_app_unknown_site_raises(self):
        with self.assertRaises(frappe.DoesNotExistError):
            site_api.install_app(site="does-not-exist.localhost", app="erpnext")

    # ---- 3. log in (Frappe-native auth on the control-plane site) -----

    def test_login_with_correct_password_succeeds(self):
        # LoginManager.authenticate sets frappe.session.user on success
        # and raises on failure.
        frappe.set_user("Administrator")  # reset session
        lm = LoginManager()
        lm.authenticate(
            user="wf-admin@barista.test",
            pwd="wf-test-password-12345",
        )
        self.assertEqual(frappe.session.user, "wf-admin@barista.test")

    def test_login_with_wrong_password_fails(self):
        frappe.set_user("Administrator")
        lm = LoginManager()
        with self.assertRaises(frappe.AuthenticationError):
            lm.authenticate(
                user="wf-admin@barista.test",
                pwd="WRONG-PASSWORD",
            )

    # ---- 4. full happy path --------------------------------------------

    def test_create_then_install_then_login(self):
        """The README workflow: spin a site, add an app, sign in.

        Privileged calls (the dm_client HTTP) are patched at the task
        boundary so this stays an in-process test.
        """
        with patch("barista.tasks.site._run_in_bench"), \
             patch("barista.tasks.site._wait_for_exec"):

            # 1. create site
            r = site_api.create(
                bench=self.BENCH,
                site_name=self.SITE,
                admin_password="full-pw-1234567890",
                mariadb_root_password="mdb",
                apps=["erpnext"],
            )
            self.assertEqual(r["site"], self.SITE)
            self.assertTrue(frappe.db.exists("Site", self.SITE))

            # 2. install another app
            r2 = site_api.install_app(site=self.SITE, app="hrms")
            self.assertEqual(
                frappe.db.get_value("Bench Action", r2["bench_action"], "action"),
                "Install App",
            )

            # 3. log in (control-plane creds)
            frappe.set_user("Administrator")
            lm = LoginManager()
            lm.authenticate(
                user="wf-admin@barista.test",
                pwd="full-pw-1234567890-different-than-site-pw" if False
                    else "wf-test-password-12345",
            )
            self.assertEqual(frappe.session.user, "wf-admin@barista.test")


class TestBenchLifecycleSmoke(FrappeTestCase):
    """Spot-check the bench API beyond what test_api.py covers."""

    BENCH = "smoke-bench"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Bench Spec", "smoke-spec"):
            frappe.get_doc({
                "doctype": "Bench Spec",
                "spec_name": "smoke-spec",
                "is_system": 1,
            }).insert(ignore_permissions=True)
        if not frappe.db.exists("Bench Host", cls.BENCH):
            frappe.get_doc({
                "doctype": "Bench Host",
                "bench_name": cls.BENCH,
                "spec": "smoke-spec",
                "status": "Running",
                "http_port": 18096,
            }).insert(ignore_permissions=True)
        if not frappe.db.exists("User", "smoke-admin@barista.test"):
            frappe.get_doc({
                "doctype": "User",
                "email": "smoke-admin@barista.test",
                "first_name": "Smoke",
                "send_welcome_email": 0,
                "roles": [{"role": "Barista Admin"}],
            }).insert(ignore_permissions=True)

    def setUp(self):
        frappe.set_user("smoke-admin@barista.test")

    def test_stop_then_start_creates_two_actions(self):
        out1 = bench_api.stop(self.BENCH)
        out2 = bench_api.start(self.BENCH)
        self.assertNotEqual(out1["bench_action"], out2["bench_action"])
        self.assertEqual(
            frappe.db.get_value("Bench Action", out1["bench_action"], "action"),
            "Stop",
        )
        self.assertEqual(
            frappe.db.get_value("Bench Action", out2["bench_action"], "action"),
            "Start",
        )
