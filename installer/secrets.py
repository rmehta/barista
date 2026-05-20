"""Password generation helper.

Tiny module so tests can monkeypatch one symbol and get deterministic
secrets in fixtures without touching the stdlib `secrets` module.
"""

import secrets as _stdlib_secrets


def random_hex(nbytes: int = 16) -> str:
    """Return `2 * nbytes` hex characters of cryptographic randomness."""
    return _stdlib_secrets.token_hex(nbytes)
