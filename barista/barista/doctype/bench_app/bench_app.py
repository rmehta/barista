import re

from frappe.model.document import Document

_URL_RX = re.compile(r"^(https?://|git@)[^\s]+$")


class BenchApp(Document):
    """A source: an app one *could* install on a bench. Like Press's
    Marketplace App but without subscriptions."""

    def validate(self) -> None:
        if not _URL_RX.match(self.repository_url or ""):
            from frappe import throw
            throw(f"repository_url must look like a Git URL (got {self.repository_url!r})")
