"""One-shot exec + interactive terminal over websocket."""

from __future__ import annotations

import secrets
import time

import docker
from flask import Blueprint, abort, jsonify, request

from . import policy
from .tasks import registry

bp = Blueprint("exec_ops", __name__)


# ---- one-shot exec ------------------------------------------------------

@bp.post("/benches/<name>/exec")
def start_exec(name: str):
    policy.validate_name(name)
    p = request.get_json(force=True)
    cmd = p.get("cmd")
    user = p.get("user", "frappe")
    timeout_s = int(p.get("timeout_s", 600))

    if not isinstance(cmd, list) or not all(isinstance(x, str) for x in cmd):
        abort(400, description="cmd must be list[str]")
    if len(cmd) > 64 or any(len(x) > 4096 for x in cmd):
        abort(400, description="cmd is too long")

    def _run(task):
        client = docker.from_env()
        container = client.containers.get(f"barista-bench-{name}")
        exec_id = client.api.exec_create(container.id, cmd, user=user, tty=False,
                                         stdout=True, stderr=True)["Id"]
        stream = client.api.exec_start(exec_id, stream=True, demux=False)
        deadline = time.time() + timeout_s
        for chunk in stream:
            if time.time() > deadline:
                task.log.append(b"\n[timeout]\n")
                break
            task.log.append(chunk if isinstance(chunk, bytes) else chunk.encode())
        info = client.api.exec_inspect(exec_id)
        return {"exit_code": info.get("ExitCode"), "running": info.get("Running")}

    task = registry.submit(kind="exec", fn=_run)
    return jsonify(exec_id=task.id), 202


@bp.get("/benches/<name>/exec/<eid>")
def get_exec(name: str, eid: str):
    policy.validate_name(name)
    return jsonify(registry.get(eid).to_dict())


@bp.get("/benches/<name>/exec/<eid>/log")
def get_exec_log(name: str, eid: str):
    policy.validate_name(name)
    since = int(request.args.get("since", 0))
    task = registry.get(eid)
    offset, data = task.log.tail(since)
    return jsonify(offset=offset, data=data.decode("utf-8", "replace"),
                   status=task.status)


# ---- interactive terminal: one-shot token + websocket -------------------

_terminal_tokens: dict[str, tuple[str, float]] = {}   # token -> (bench, expires_at)
_TOKEN_TTL = 60


@bp.post("/terminal-tokens")
def mint_terminal_token():
    p = request.get_json(force=True)
    bench = policy.validate_name(p.get("bench", ""))
    token = secrets.token_urlsafe(24)
    _terminal_tokens[token] = (bench, time.time() + _TOKEN_TTL)
    _gc_tokens()
    return jsonify(token=token, expires_in=_TOKEN_TTL,
                   ws_url=f"/v1/terminal?token={token}")


def _gc_tokens():
    now = time.time()
    stale = [t for t, (_, exp) in _terminal_tokens.items() if exp < now]
    for t in stale:
        _terminal_tokens.pop(t, None)


@bp.route("/terminal")
def terminal_ws():
    """gevent-websocket route.

    The frontend connects with the one-shot token. We then attach a
    docker exec stream to the websocket in both directions. Closing
    the WS kills the exec.
    """
    token = request.args.get("token", "")
    _gc_tokens()
    pair = _terminal_tokens.pop(token, None)
    if not pair:
        abort(401, description="bad or expired terminal token")
    bench, _ = pair

    ws = request.environ.get("wsgi.websocket")
    if ws is None:
        abort(400, description="expected websocket upgrade")

    client = docker.from_env()
    container = client.containers.get(f"barista-bench-{bench}")
    exec_id = client.api.exec_create(
        container.id, ["bash", "-l"], user="frappe",
        tty=True, stdout=True, stderr=True, stdin=True,
    )["Id"]
    sock = client.api.exec_start(exec_id, tty=True, socket=True, demux=False)
    raw = sock._sock if hasattr(sock, "_sock") else sock   # docker-py quirk

    import gevent

    def pump_from_container():
        while not ws.closed:
            try:
                data = raw.recv(4096)
            except OSError:
                break
            if not data:
                break
            ws.send(data.decode("utf-8", "replace"))

    def pump_to_container():
        while not ws.closed:
            msg = ws.receive()
            if msg is None:
                break
            raw.sendall(msg.encode() if isinstance(msg, str) else msg)

    gevent.joinall([gevent.spawn(pump_from_container),
                    gevent.spawn(pump_to_container)])
    try:
        raw.close()
    except OSError:
        pass
    return ("", 200)
