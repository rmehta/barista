"""Bench lifecycle endpoints — the bulk of what Barista calls.

Every container created here carries a `barista.role` label so we
can find ours back later without polluting other workloads on the
same daemon.
"""

from __future__ import annotations

import json
import os
import threading
import time

import docker
from docker.errors import APIError, NotFound
from flask import Blueprint, abort, current_app, jsonify, request

from . import policy

bp = Blueprint("manager", __name__)

_LABEL_ROLE = "barista.role"
_LABEL_BENCH = "barista.bench"
_LABEL_SPEC = "barista.spec"

# one RLock per bench-name; lifecycle ops on the same bench serialise
_bench_locks: dict[str, threading.RLock] = {}
_bench_locks_lock = threading.Lock()


def _client() -> docker.DockerClient:
    return docker.from_env()


client = _client  # exported for app.py boot


def docker_version() -> str:
    try:
        return _client().version().get("Version", "unknown")
    except Exception:  # noqa: BLE001
        return "unreachable"


def docker_info() -> dict:
    return _client().info()


def _lock_for(name: str) -> threading.RLock:
    with _bench_locks_lock:
        lk = _bench_locks.get(name)
        if lk is None:
            lk = threading.RLock()
            _bench_locks[name] = lk
        return lk


def _container_name(bench_name: str) -> str:
    return f"barista-bench-{bench_name}"


def _container(bench_name: str):
    try:
        return _client().containers.get(_container_name(bench_name))
    except NotFound:
        abort(404, description=f"no such bench: {bench_name}")


# ---- list / inspect ------------------------------------------------------

@bp.get("/benches")
def list_benches():
    out = []
    for c in _client().containers.list(all=True,
                                       filters={"label": f"{_LABEL_ROLE}=bench"}):
        out.append(_summarise(c))
    return jsonify(out)


@bp.get("/benches/<name>")
def inspect_bench(name: str):
    policy.validate_name(name)
    return jsonify(_summarise(_container(name)))


def _summarise(c) -> dict:
    c.reload()
    state = c.attrs["State"]
    return {
        "name": c.labels.get(_LABEL_BENCH, c.name.removeprefix("barista-bench-")),
        "container_id": c.id[:12],
        "image": c.image.tags[0] if c.image.tags else c.image.id,
        "status": state["Status"],            # running, exited, ...
        "health": (state.get("Health") or {}).get("Status"),
        "started_at": state.get("StartedAt"),
        "spec": c.labels.get(_LABEL_SPEC),
        "ports": {
            internal: bindings[0]["HostPort"] if bindings else None
            for internal, bindings in (c.attrs["NetworkSettings"]["Ports"] or {}).items()
        },
    }


# ---- create --------------------------------------------------------------

@bp.post("/benches")
def create_bench():
    p = request.get_json(force=True)
    name = policy.validate_name(p.get("name", ""))
    image = policy.validate_image(p.get("image", ""))
    host_path = policy.validate_host_path(p.get("host_path", ""),
                                          current_app.config["DATA_ROOT"])
    http_port = policy.validate_port(p.get("http_port"))
    cpu_quota = float(p.get("cpu_quota") or 0)
    mem_limit_mb = int(p.get("mem_limit_mb") or 0)
    caps = policy.validate_caps(p.get("cap_add"))

    policy.reject_dangerous(p)

    labels = {
        _LABEL_ROLE: "bench",
        _LABEL_BENCH: name,
    }
    if spec := p.get("spec"):
        labels[_LABEL_SPEC] = str(spec)

    traefik = p.get("traefik") or {}
    if traefik.get("host"):
        labels["traefik.enable"] = "true"
        labels[f"traefik.http.routers.{name}.rule"] = f"Host(`{traefik['host']}`)"
        labels[f"traefik.http.services.{name}.loadbalancer.server.port"] = "80"
        if traefik.get("tls"):
            labels[f"traefik.http.routers.{name}.entrypoints"] = "websecure"
            labels[f"traefik.http.routers.{name}.tls.certresolver"] = "le"

    extra_labels = p.get("labels") or {}
    for k, v in extra_labels.items():
        # policy: only labels under `barista.*` are allowed from callers
        if not str(k).startswith("barista."):
            abort(400, description=f"label key not allowed: {k}")
        labels[str(k)] = str(v)

    with _lock_for(name):
        try:
            existing = _client().containers.get(_container_name(name))
            return jsonify(_summarise(existing)), 200
        except NotFound:
            pass

        host_config = {
            "binds": [
                f"{host_path}:/home/frappe/bench",
                # `/backups` is the standard mount the control plane
                # also gets; benches get a per-bench backup dir.
                f"{host_path}/.backups:/backups",
            ],
            "port_bindings": {"80/tcp": [("127.0.0.1", http_port)]},
            "restart_policy": {"Name": "unless-stopped"},
            "cap_drop": ["ALL"],
            "cap_add": caps or ["CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE"],
            "security_opt": ["no-new-privileges"],
            "tmpfs": {"/tmp": "rw,size=128m"},
        }
        if cpu_quota > 0:
            host_config["nano_cpus"] = int(cpu_quota * 1e9)
        if mem_limit_mb > 0:
            host_config["mem_limit"] = mem_limit_mb * 1024 * 1024

        try:
            c = _client().containers.run(
                image,
                name=_container_name(name),
                detach=True,
                network=os.environ.get("NETWORK", "barista-net"),
                labels=labels,
                read_only=False,  # bench writes a lot; sandbox via cap_drop instead
                **host_config,
            )
        except APIError as e:
            abort(400, description=f"docker error: {e.explanation or e}")

        return jsonify(_summarise(c)), 201


# ---- lifecycle -----------------------------------------------------------

@bp.post("/benches/<name>/start")
def start_bench(name: str):
    policy.validate_name(name)
    with _lock_for(name):
        c = _container(name)
        c.start()
        return jsonify(_summarise(c))


@bp.post("/benches/<name>/stop")
def stop_bench(name: str):
    policy.validate_name(name)
    timeout = int(request.args.get("timeout", 10))
    with _lock_for(name):
        c = _container(name)
        c.stop(timeout=timeout)
        return jsonify(_summarise(c))


@bp.post("/benches/<name>/restart")
def restart_bench(name: str):
    policy.validate_name(name)
    timeout = int(request.args.get("timeout", 10))
    with _lock_for(name):
        c = _container(name)
        c.restart(timeout=timeout)
        return jsonify(_summarise(c))


@bp.post("/benches/<name>/update")
def update_bench(name: str):
    policy.validate_name(name)
    p = request.get_json(force=True)
    kw = {}
    if "cpu_quota" in p:
        kw["nano_cpus"] = int(float(p["cpu_quota"]) * 1e9)
    if "mem_limit_mb" in p:
        kw["mem_limit"] = int(p["mem_limit_mb"]) * 1024 * 1024
    with _lock_for(name):
        c = _container(name)
        c.update(**kw)
        return jsonify(_summarise(c))


@bp.delete("/benches/<name>")
def destroy_bench(name: str):
    policy.validate_name(name)
    force = request.args.get("force", "0") in ("1", "true", "yes")
    with _lock_for(name):
        c = _container(name)
        c.remove(force=force, v=False)   # never remove anonymous vols
        return jsonify(ok=True)


# ---- live state ---------------------------------------------------------

@bp.get("/benches/<name>/logs")
def container_logs(name: str):
    policy.validate_name(name)
    tail = int(request.args.get("tail", 200))
    since = request.args.get("since")
    c = _container(name)
    kwargs = {"tail": tail, "timestamps": True}
    if since:
        kwargs["since"] = int(float(since))
    data = c.logs(**kwargs).decode("utf-8", "replace")
    return jsonify(lines=data.splitlines())


@bp.get("/benches/<name>/stats")
def container_stats(name: str):
    policy.validate_name(name)
    c = _container(name)
    s = c.stats(stream=False)
    return jsonify(_compute_stats(s))


def _compute_stats(s: dict) -> dict:
    """One-shot CPU% + MB from a Docker stats sample."""
    try:
        cpu = s["cpu_stats"]["cpu_usage"]["total_usage"]
        pre = s["precpu_stats"]["cpu_usage"]["total_usage"]
        sys = s["cpu_stats"]["system_cpu_usage"]
        psy = s["precpu_stats"].get("system_cpu_usage", 0)
        online = s["cpu_stats"].get("online_cpus") or 1
        cpu_pct = ((cpu - pre) / (sys - psy)) * online * 100 if sys > psy else 0.0
    except KeyError:
        cpu_pct = 0.0
    mem = s.get("memory_stats", {}).get("usage", 0) / (1024 * 1024)
    return {"ts": time.time(), "cpu_pct": cpu_pct, "mem_mb": mem,
            "raw_keys": sorted(s.keys())}


# ---- networks -----------------------------------------------------------

@bp.post("/networks/ensure")
def ensure_network():
    p = request.get_json(force=True)
    name = p.get("name", "barista-net")
    try:
        n = _client().networks.get(name)
    except NotFound:
        n = _client().networks.create(name, driver="bridge")
    cfg = n.attrs["IPAM"]["Config"] or []
    return jsonify(id=n.id, subnet=(cfg[0]["Subnet"] if cfg else None))
