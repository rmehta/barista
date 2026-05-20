"""Request-level access control: token + IP allowlist."""

from __future__ import annotations

import hmac
import ipaddress
import logging

from flask import abort, current_app, request

_OPEN_PATHS = {"/v1/health"}  # also requires token; just doesn't log noisily


def before_request():
    if request.method == "OPTIONS":
        return  # CORS preflight; the API isn't reachable from browsers anyway

    _enforce_cidr()
    _enforce_token()


def _enforce_cidr():
    src = _client_ip()
    cidrs = current_app.config["ALLOWED_CIDRS"]
    addr = ipaddress.ip_address(src)
    for cidr in cidrs:
        if addr in ipaddress.ip_network(cidr, strict=False):
            return
    logging.warning("rejecting %s — not in %s", src, cidrs)
    abort(403, description="source IP not allowed")


def _enforce_token():
    sent = request.headers.get("X-Auth-Token", "")
    expected = current_app.config["TOKEN"]
    if not sent or not hmac.compare_digest(sent, expected):
        if request.path not in _OPEN_PATHS:
            logging.warning("bad token from %s on %s", _client_ip(), request.path)
        abort(401, description="invalid token")


def _client_ip() -> str:
    # X-Forwarded-For is ignored on purpose — we are not behind a proxy.
    # The reverse-proxy (traefik) is on the other side of the network
    # boundary; nothing should be forwarding to this service.
    return request.remote_addr or "0.0.0.0"
