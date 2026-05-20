"""Flask app for the Barista docker-manager service.

Exposes a small HTTP API the Barista control plane uses to drive
Docker. Access is gated by:

  1. Network: this service is on `barista-net` only; no published
     ports. (Enforced by docker-compose, not by this code.)
  2. Bearer token in `X-Auth-Token`; the secret lives in
     `BARISTA_DOCKER_MANAGER_TOKEN`.
  3. IP allowlist: the client's source IP must be inside one of the
     subnets in `BARISTA_DM_ALLOWED_CIDRS` (defaults to the
     `barista-net` subnet looked up at boot).

See ../specs/09-docker-manager.md for the full spec.
"""

from __future__ import annotations

import logging
import os

from flask import Flask, jsonify

from . import auth, builds, exec_ops, manager, routes, tasks


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["TOKEN"] = os.environ["BARISTA_DOCKER_MANAGER_TOKEN"]
    app.config["ALLOWED_CIDRS"] = _load_allowed_cidrs()
    app.config["DATA_ROOT"] = os.environ.get("BARISTA_DATA_ROOT", "/data")
    app.config["TRAEFIK_DYNAMIC"] = os.environ.get(
        "BARISTA_TRAEFIK_DYNAMIC", "/etc/traefik/dynamic.yml"
    )

    logging.basicConfig(
        level=os.environ.get("BARISTA_DM_LOG_LEVEL", "INFO"),
        format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":%(message)r}',
    )

    app.before_request(auth.before_request)
    app.register_error_handler(Exception, _error_handler)

    @app.get("/v1/health")
    def health():
        return jsonify(ok=True, docker_version=manager.docker_version())

    @app.get("/v1/info")
    def info():
        return jsonify(manager.docker_info())

    app.register_blueprint(builds.bp,    url_prefix="/v1")
    app.register_blueprint(manager.bp,   url_prefix="/v1")
    app.register_blueprint(exec_ops.bp,  url_prefix="/v1")
    app.register_blueprint(routes.bp,    url_prefix="/v1")
    app.register_blueprint(tasks.bp,     url_prefix="/v1")

    return app


def _load_allowed_cidrs() -> list[str]:
    env = os.environ.get("BARISTA_DM_ALLOWED_CIDRS", "").strip()
    if env:
        return [c.strip() for c in env.split(",") if c.strip()]

    # discover our own bridge network's subnet
    try:
        net = manager.client().networks.get(os.environ.get("NETWORK", "barista-net"))
        cidrs = [c["Subnet"] for c in net.attrs["IPAM"]["Config"] if c.get("Subnet")]
        if cidrs:
            return cidrs
    except Exception as e:  # noqa: BLE001 — defensive at boot
        logging.warning("could not auto-detect allowed CIDRs: %s", e)

    # last resort: localhost only (Unix-socket / loopback bind)
    return ["127.0.0.0/8"]


def _error_handler(e):
    from werkzeug.exceptions import HTTPException

    if isinstance(e, HTTPException):
        return jsonify(error=e.name, message=e.description), e.code

    logging.exception("unhandled")
    return jsonify(error="internal", message=str(e)), 500
