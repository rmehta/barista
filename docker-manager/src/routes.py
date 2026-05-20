"""Traefik dynamic config writer.

Barista pushes the full list of routes it wants; we render the YAML
file and Traefik picks it up via its filesystem watcher. No restart.
"""

from __future__ import annotations

import os
import tempfile

import yaml
from flask import Blueprint, abort, current_app, jsonify, request

bp = Blueprint("routes", __name__)


@bp.put("/routes")
def replace_routes():
    p = request.get_json(force=True)
    routes = p.get("routes")
    if not isinstance(routes, list):
        abort(400, description="routes must be a list")

    http_routers, http_services = {}, {}

    for r in routes:
        name = r.get("service")
        host = r.get("host")
        port = r.get("port", 80)
        if not name or not host:
            abort(400, description=f"route missing service/host: {r}")
        rid = name
        router = {
            "rule": f"Host(`{host}`)",
            "service": rid,
            "entryPoints": ["websecure" if r.get("tls") else "web"],
        }
        if r.get("tls"):
            router["tls"] = {"certResolver": "le"}
        http_routers[rid] = router
        http_services[rid] = {
            "loadBalancer": {"servers": [{"url": f"http://{name}:{port}"}]}
        }

    doc = {"http": {"routers": http_routers, "services": http_services}}
    out_path = current_app.config["TRAEFIK_DYNAMIC"]

    # atomic write
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(out_path) or ".",
                                prefix=".dynamic.", suffix=".yml")
    with os.fdopen(fd, "w") as f:
        yaml.safe_dump(doc, f, sort_keys=True)
    os.replace(tmp, out_path)

    return jsonify(applied=len(routes))
