"""In-memory long-running task table.

A task is anything that takes longer than a few seconds (build,
pull, exec). Each one gets a uuid and a log ring buffer; callers
poll status / tail logs by id.

Survives only as long as the process. If docker-manager restarts,
in-flight tasks vanish — Barista's job pattern treats that as a
generic failure and retries (every long op is idempotent by design).
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from flask import Blueprint, abort, current_app, jsonify, request

bp = Blueprint("tasks", __name__)


class _LogBuffer:
    """A bounded byte buffer with monotonically-increasing offsets so
    callers can resume from where they left off."""

    def __init__(self, max_bytes: int = 5 * 1024 * 1024):
        self._lock = threading.Lock()
        self._chunks: deque[tuple[int, bytes]] = deque()
        self._total = 0
        self._size = 0
        self._max = max_bytes

    def append(self, data: bytes) -> None:
        if not data:
            return
        with self._lock:
            self._chunks.append((self._total, data))
            self._total += len(data)
            self._size += len(data)
            while self._size > self._max and self._chunks:
                _, dropped = self._chunks.popleft()
                self._size -= len(dropped)

    def tail(self, since: int = 0) -> tuple[int, bytes]:
        with self._lock:
            out = bytearray()
            new_offset = self._total
            for offset, chunk in self._chunks:
                if offset + len(chunk) <= since:
                    continue
                if offset >= since:
                    out.extend(chunk)
                else:
                    out.extend(chunk[since - offset:])
            return new_offset, bytes(out)


class Task:
    __slots__ = ("id", "kind", "status", "started_at", "finished_at",
                 "error", "result", "log", "future")

    def __init__(self, kind: str):
        self.id = f"{kind[:1]}-{uuid.uuid4().hex[:12]}"
        self.kind = kind
        self.status: str = "running"
        self.started_at = time.time()
        self.finished_at: float | None = None
        self.error: str | None = None
        self.result: Any = None
        self.log = _LogBuffer()
        self.future: Future | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": (self.finished_at or time.time()) - self.started_at,
            "error": self.error,
            "result": self.result,
        }


class _Registry:
    def __init__(self, max_workers: int = 4, ttl_s: int = 30 * 60):
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}
        self._ttl = ttl_s
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dm")

    def submit(self, kind: str, fn: Callable[[Task], Any]) -> Task:
        task = Task(kind)

        def _run():
            try:
                task.result = fn(task)
                task.status = "success"
            except Exception as e:  # noqa: BLE001 — we report everything
                task.status = "failure"
                task.error = repr(e)
                task.log.append(f"\nERROR: {e!r}\n".encode())
                current_app.logger.exception("task %s failed", task.id)
            finally:
                task.finished_at = time.time()

        task.future = self._pool.submit(_run)
        with self._lock:
            self._tasks[task.id] = task
            self._gc_locked()
        return task

    def get(self, tid: str) -> Task:
        with self._lock:
            t = self._tasks.get(tid)
        if not t:
            abort(404, description=f"unknown task: {tid}")
        return t

    def cancel(self, tid: str) -> Task:
        t = self.get(tid)
        if t.future and not t.future.done():
            # ThreadPoolExecutor.cancel() only works if the task hasn't
            # started yet. For running tasks we just flag and let the
            # worker check.
            t.future.cancel()
            t.status = "cancelled"
        return t

    def coalesce(self, key: str, kind: str,
                 fn: Callable[[Task], Any]) -> Task:
        """Submit, OR return an existing running task with the same key."""
        with self._lock:
            for t in self._tasks.values():
                if t.status == "running" and t.kind == kind and t.result == key:
                    return t
        task = self.submit(kind, fn)
        # remember the coalesce key as the prospective result so a
        # second caller with the same key finds it
        task.result = key
        return task

    def _gc_locked(self):
        now = time.time()
        stale = [tid for tid, t in self._tasks.items()
                 if t.finished_at and now - t.finished_at > self._ttl]
        for tid in stale:
            self._tasks.pop(tid, None)


registry = _Registry()


# ---- HTTP endpoints common to all task kinds ------------------------

@bp.get("/tasks/<tid>")
def get_task(tid: str):
    return jsonify(registry.get(tid).to_dict())


@bp.get("/tasks/<tid>/log")
def get_task_log(tid: str):
    since = int(request.args.get("since", 0))
    task = registry.get(tid)
    offset, data = task.log.tail(since)
    return jsonify(offset=offset, data=data.decode("utf-8", "replace"))


@bp.delete("/tasks/<tid>")
def delete_task(tid: str):
    return jsonify(registry.cancel(tid).to_dict())
