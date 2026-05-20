"""Shared fixtures for pure-Python unit tests.

These tests do NOT require a Frappe site. We stub `frappe` at
collection time so test modules can `import frappe` at the top.
"""

import sys
import types


def _install_fake_frappe() -> None:
    if "frappe" in sys.modules and not getattr(sys.modules["frappe"], "__fake__", False):
        return  # real frappe present — leave it alone

    fake = types.ModuleType("frappe")
    fake.__fake__ = True
    fake.conf = {}
    fake.local = types.SimpleNamespace()

    def throw(msg, exc=None):
        raise (exc or RuntimeError)(msg)

    class ValidationError(Exception):
        pass

    class DoesNotExistError(Exception):
        pass

    class PermissionError(Exception):  # noqa: A001 — stub
        pass

    fake.throw = throw
    fake.log_error = lambda **kw: None
    fake.ValidationError = ValidationError
    fake.DoesNotExistError = DoesNotExistError
    fake.PermissionError = PermissionError
    fake.get_roles = lambda: []
    fake._ = lambda s: s  # i18n shim

    sys.modules["frappe"] = fake


_install_fake_frappe()
