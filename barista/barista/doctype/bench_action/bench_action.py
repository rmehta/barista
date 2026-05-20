import frappe
from frappe.model.document import Document


class BenchAction(Document):
    """The audit trail. One row per privileged operation. Inserted by
    API methods, updated by tasks, read-only from the UI."""

    def before_insert(self) -> None:
        if not self.triggered_by:
            self.triggered_by = frappe.session.user
        if not self.triggered_at:
            from frappe.utils import now_datetime
            self.triggered_at = now_datetime()

    def mark_running(self) -> None:
        self.status = "Running"
        self.save(ignore_permissions=True)
        self._publish()

    def mark_success(self, log: str | None = None) -> None:
        self._finish("Success", log=log)

    def mark_failure(self, error: str, log: str | None = None) -> None:
        self._finish("Failure", log=log, error=error)

    def append_log(self, chunk: str) -> None:
        self.log = ((self.log or "") + chunk)[-1_000_000:]
        self.db_set("log", self.log, update_modified=False)

    def _finish(self, status: str, log: str | None = None,
                error: str | None = None) -> None:
        from frappe.utils import now_datetime
        self.status = status
        if log:
            self.log = log
        if error:
            self.error = error
        if self.triggered_at:
            self.duration_s = int(
                (now_datetime() - self.triggered_at).total_seconds()
            )
        self.save(ignore_permissions=True)
        self._publish()

    def _publish(self) -> None:
        frappe.publish_realtime(
            f"action:{self.name}",
            {
                "name": self.name,
                "status": self.status,
                "target_type": self.target_type,
                "target": self.target,
                "action": self.action,
                "duration_s": self.duration_s,
            },
        )
