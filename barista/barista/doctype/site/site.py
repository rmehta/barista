import hashlib
import re
import secrets

import frappe
from frappe.model.document import Document

_NAME_RX = re.compile(r"^[a-z][a-z0-9.-]{2,63}$")


class Site(Document):
    """A Frappe site on a Bench Host."""

    def before_insert(self) -> None:
        if not self.created_on:
            from frappe.utils import now_datetime
            self.created_on = now_datetime()
        if not self.db_name:
            self.db_name = self._derive_db_name()
        if not self.service_token:
            self.service_token = secrets.token_urlsafe(32)

    def validate(self) -> None:
        self._validate_name()

    def on_trash(self) -> None:
        if self.is_control_plane:
            frappe.throw("Cannot delete the control-plane site.")

    def publish_status(self) -> None:
        frappe.publish_realtime(
            f"site:{self.name}:status",
            {"status": self.status},
        )

    # ---- helpers ----

    def _validate_name(self) -> None:
        if not _NAME_RX.match(self.site_name or ""):
            frappe.throw(
                f"site_name must look like a hostname "
                f"(got {self.site_name!r})"
            )

    def _derive_db_name(self) -> str:
        return "_" + hashlib.sha256(self.site_name.encode()).hexdigest()[:15]
