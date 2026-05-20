from frappe.model.document import Document


class BaristaSettings(Document):
    def validate(self) -> None:
        if self.http_port_range_start and self.http_port_range_start < 1024:
            from frappe import throw
            throw("HTTP port range must start at 1024 or above")
        if self.max_concurrent_builds and self.max_concurrent_builds < 1:
            from frappe import throw
            throw("Max concurrent builds must be at least 1")
