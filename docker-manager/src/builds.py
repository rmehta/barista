"""Image builds & pulls — long-running, streamed through the task table."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import docker
from docker.errors import APIError, BuildError
from flask import Blueprint, abort, jsonify, request

from . import policy
from .tasks import registry

bp = Blueprint("builds", __name__)


@bp.post("/builds")
def start_build():
    p = request.get_json(force=True)
    tag = policy.validate_image(p.get("tag", ""))
    dockerfile = p.get("dockerfile") or ""
    build_args = p.get("build_args") or {}
    context_files = p.get("context_files") or {}

    if not dockerfile.strip():
        abort(400, description="missing dockerfile")

    # coalesce concurrent builds for the same tag
    def _build(task):
        with tempfile.TemporaryDirectory(prefix="dm-build-") as td:
            td_path = Path(td)
            (td_path / "Dockerfile").write_text(dockerfile)
            for rel, contents in context_files.items():
                # path traversal: forbid absolute and "../"
                if rel.startswith("/") or ".." in Path(rel).parts:
                    raise ValueError(f"bad context filename: {rel}")
                dest = td_path / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(contents)

            client = docker.from_env()
            stream = client.api.build(
                path=str(td_path),
                tag=tag,
                buildargs=build_args,
                rm=True,
                forcerm=True,
                decode=True,
            )
            for evt in stream:
                if "stream" in evt:
                    task.log.append(evt["stream"].encode("utf-8", "replace"))
                elif "errorDetail" in evt:
                    raise BuildError(evt["errorDetail"].get("message", "build failed"), stream)
                elif "status" in evt:
                    task.log.append(
                        f"{evt.get('status','')}: {evt.get('progress','')}\n".encode()
                    )
        return {"tag": tag}

    task = registry.coalesce(key=tag, kind="build", fn=_build)
    return jsonify(build_id=task.id, tag=tag, coalesced=task.result == tag), 202


@bp.get("/builds/<tid>")
def get_build(tid: str):
    return jsonify(registry.get(tid).to_dict())


@bp.get("/builds/<tid>/log")
def get_build_log(tid: str):
    since = int(request.args.get("since", 0))
    task = registry.get(tid)
    offset, data = task.log.tail(since)
    return jsonify(offset=offset, data=data.decode("utf-8", "replace"),
                   status=task.status)


@bp.delete("/builds/<tid>")
def cancel_build(tid: str):
    return jsonify(registry.cancel(tid).to_dict())


@bp.post("/images/pull")
def pull_image():
    p = request.get_json(force=True)
    ref = policy.validate_image(p.get("ref", ""))

    def _pull(task):
        client = docker.from_env()
        for evt in client.api.pull(ref, stream=True, decode=True):
            line = json.dumps(evt) + "\n"
            task.log.append(line.encode())
            if "errorDetail" in evt:
                raise APIError(evt["errorDetail"].get("message", "pull failed"))
        return {"ref": ref}

    task = registry.coalesce(key=ref, kind="pull", fn=_pull)
    return jsonify(pull_id=task.id, ref=ref), 202
