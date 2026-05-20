import re

import frappe
from frappe.model.document import Document

from barista.exceptions import BenchInUseError

_NAME_RX = re.compile(r"^[a-z][a-z0-9-]{1,30}$")


class BenchHost(Document):
    """A live Docker container running a bench."""

    def validate(self) -> None:
        self._validate_name()
        if not self.created_on:
            from frappe.utils import now_datetime
            self.created_on = now_datetime()

    def on_trash(self) -> None:
        self._block_if_in_use()

    def publish_status(self) -> None:
        frappe.publish_realtime(
            f"bench:{self.name}:status",
            {"status": self.status, "container_id": self.container_id},
        )

    # ---- helpers ----

    def _validate_name(self) -> None:
        if not _NAME_RX.match(self.bench_name or ""):
            frappe.throw(
                f"bench_name must match {_NAME_RX.pattern!r} "
                f"(got {self.bench_name!r})"
            )

    def _block_if_in_use(self) -> None:
        active = frappe.db.count("Site", {
            "bench": self.name,
            "status": ["!=", "Archived"],
        })
        if active:
            raise BenchInUseError(
                f"Bench {self.name!r} has {active} non-archived site(s); archive "
                "them before destroying the bench."
            )
