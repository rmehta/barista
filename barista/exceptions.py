"""Barista-specific exceptions. All subclass frappe.ValidationError so
they render as HTTP 417 with a friendly message in the UI."""

import frappe


class BaristaError(frappe.ValidationError):
    """Base class for Barista errors."""


class DockerManagerError(BaristaError):
    """Something went wrong calling barista-docker-manager."""


class BenchInUseError(BaristaError):
    """Bench has non-archived sites and cannot be destroyed."""


class InvalidBenchSpec(BaristaError):
    """A bench spec is missing required fields or has invalid app order."""
