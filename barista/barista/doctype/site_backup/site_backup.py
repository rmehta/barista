from frappe.model.document import Document


class SiteBackup(Document):
    """One backup of one site. Created by the backup task; rows are
    immutable from the UI."""

    def before_insert(self) -> None:
        if not self.started_at:
            from frappe.utils import now_datetime
            self.started_at = now_datetime()

    def mark_done(self, path: str, size_mb: float) -> None:
        from frappe.utils import now_datetime
        self.status = "Success"
        self.path = path
        self.size_mb = size_mb
        self.finished_at = now_datetime()
        self.save(ignore_permissions=True)

    def mark_failed(self) -> None:
        from frappe.utils import now_datetime
        self.status = "Failure"
        self.finished_at = now_datetime()
        self.save(ignore_permissions=True)
