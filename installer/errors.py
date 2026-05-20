"""Installer exception hierarchy."""


class InstallerError(Exception):
    """Anything we can't recover from. main() catches it and exits 1."""
