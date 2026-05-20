import frappe
from frappe.model.document import Document

from barista.exceptions import InvalidBenchSpec


class BenchSpec(Document):
    """Recipe for a bench image: app list, Python/Node versions, base image."""

    def validate(self) -> None:
        self._validate_apps()
        self._normalise_apps()

    def on_trash(self) -> None:
        self._block_if_in_use()

    # ---- helpers ----

    def _validate_apps(self) -> None:
        if self.is_system:
            return
        names = [a.app_name for a in self.apps or []]
        if not names:
            raise InvalidBenchSpec("A Bench Spec must include at least one app.")
        if "frappe" not in names:
            raise InvalidBenchSpec("Every Bench Spec must include 'frappe'.")
        if len(set(names)) != len(names):
            raise InvalidBenchSpec("Duplicate apps are not allowed.")

    def _normalise_apps(self) -> None:
        """Ensure frappe is index 0 and idx is monotonic."""
        if not self.apps:
            return
        apps = sorted(self.apps, key=lambda a: (a.app_name != "frappe", a.idx or 0))
        for i, app in enumerate(apps, start=1):
            app.idx = i
        self.apps = apps

    def _block_if_in_use(self) -> None:
        if frappe.db.exists("Bench Host", {"spec": self.name}):
            frappe.throw(f"Bench Spec '{self.name}' is in use by one or more Bench Hosts.")
