import frappe
from frappe.model.document import Document


class BenchBuild(Document):
    """A single image-build event. Updated by the build task as it
    progresses; the UI subscribes to build:<name>:log."""

    def mark_running(self) -> None:
        from frappe.utils import now_datetime
        self.status = "Running"
        self.started_at = now_datetime()
        self.save(ignore_permissions=True)

    def mark_finished(self, success: bool, image_tag: str | None = None,
                      error: str | None = None) -> None:
        from frappe.utils import now_datetime
        self.status = "Success" if success else "Failure"
        self.finished_at = now_datetime()
        if self.started_at:
            self.duration_s = int(
                (self.finished_at - self.started_at).total_seconds()
            )
        if image_tag:
            self.image_tag = image_tag
        if error:
            self.build_log = (self.build_log or "") + f"\n\nERROR: {error}\n"
        self.save(ignore_permissions=True)
        frappe.publish_realtime(
            f"build:{self.name}:status",
            {"status": self.status, "duration_s": self.duration_s},
        )

    def append_log(self, chunk: str) -> None:
        # Cap at ~5 MB to match docker-manager's buffer.
        self.build_log = ((self.build_log or "") + chunk)[-5_000_000:]
        self.db_set("build_log", self.build_log, update_modified=False)
        frappe.publish_realtime(f"build:{self.name}:log", {"chunk": chunk})
