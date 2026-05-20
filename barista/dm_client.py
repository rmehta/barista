"""Thin HTTP client for barista-docker-manager.

The Frappe app never imports `docker`. Every Docker operation goes
through this client, which calls the privileged microservice over the
internal `barista-net` network.

Only the `barista-agent` queue worker has `barista_docker_manager_url`
and `_token` in its environment — calling from any other process will
raise immediately.
"""

from __future__ import annotations

from typing import Any

import frappe
import requests

from .exceptions import DockerManagerError


class DockerManagerClient:
    """One instance per request. Reads URL + token from site config /
    environment. Methods are short by design — the API mirrors the
    HTTP surface 1:1."""

    DEFAULT_TIMEOUT_S = 30

    def __init__(self, url: str | None = None, token: str | None = None,
                 timeout: int | None = None):
        self.url = (url or frappe.conf.get("barista_docker_manager_url") or "").rstrip("/")
        self.token = token or frappe.conf.get("barista_docker_manager_token") or ""
        self.timeout = timeout or self.DEFAULT_TIMEOUT_S

        if not self.url or not self.token:
            raise DockerManagerError(
                "docker-manager URL/token not configured — set "
                "barista_docker_manager_url and barista_docker_manager_token "
                "in site_config.json (this client is meant for the "
                "barista-agent worker only)."
            )

    # ---- low-level ----------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = kwargs.pop("headers", {}) or {}
        headers["X-Auth-Token"] = self.token
        try:
            resp = requests.request(
                method,
                f"{self.url}{path}",
                headers=headers,
                timeout=kwargs.pop("timeout", self.timeout),
                **kwargs,
            )
        except requests.RequestException as e:
            raise DockerManagerError(f"docker-manager unreachable: {e}") from e

        if resp.status_code >= 400:
            raise DockerManagerError(
                f"{method} {path} → {resp.status_code}: {resp.text[:500]}"
            )
        return resp.json() if resp.content else None

    # ---- health -------------------------------------------------------

    def health(self) -> dict:
        return self._request("GET", "/v1/health", timeout=5)

    # ---- benches ------------------------------------------------------

    def list_benches(self) -> list[dict]:
        return self._request("GET", "/v1/benches") or []

    def get_bench(self, name: str) -> dict:
        return self._request("GET", f"/v1/benches/{name}")

    def create_bench(self, **body: Any) -> dict:
        return self._request("POST", "/v1/benches", json=body)

    def start_bench(self, name: str) -> dict:
        return self._request("POST", f"/v1/benches/{name}/start")

    def stop_bench(self, name: str, timeout: int = 10) -> dict:
        return self._request("POST", f"/v1/benches/{name}/stop",
                             params={"timeout": timeout})

    def restart_bench(self, name: str) -> dict:
        return self._request("POST", f"/v1/benches/{name}/restart")

    def update_bench(self, name: str, **body: Any) -> dict:
        return self._request("POST", f"/v1/benches/{name}/update", json=body)

    def destroy_bench(self, name: str, force: bool = False) -> dict:
        return self._request("DELETE", f"/v1/benches/{name}",
                             params={"force": str(force).lower()})

    def stats(self, name: str) -> dict:
        return self._request("GET", f"/v1/benches/{name}/stats", timeout=5)

    def container_logs(self, name: str, tail: int = 200) -> dict:
        return self._request("GET", f"/v1/benches/{name}/logs",
                             params={"tail": tail})

    # ---- builds -------------------------------------------------------

    def start_build(self, tag: str, dockerfile: str,
                    context_files: dict[str, str] | None = None,
                    build_args: dict[str, str] | None = None) -> dict:
        return self._request("POST", "/v1/builds", json={
            "tag": tag,
            "dockerfile": dockerfile,
            "context_files": context_files or {},
            "build_args": build_args or {},
        })

    def build_status(self, build_id: str) -> dict:
        return self._request("GET", f"/v1/builds/{build_id}")

    def build_log(self, build_id: str, since: int = 0) -> dict:
        return self._request("GET", f"/v1/builds/{build_id}/log",
                             params={"since": since})

    # ---- exec ---------------------------------------------------------

    def exec_oneshot(self, bench: str, cmd: list[str], user: str = "frappe",
                     timeout_s: int = 600) -> dict:
        return self._request("POST", f"/v1/benches/{bench}/exec",
                             json={"cmd": cmd, "user": user, "timeout_s": timeout_s})

    def exec_status(self, bench: str, exec_id: str) -> dict:
        return self._request("GET", f"/v1/benches/{bench}/exec/{exec_id}")

    def exec_log(self, bench: str, exec_id: str, since: int = 0) -> dict:
        return self._request("GET", f"/v1/benches/{bench}/exec/{exec_id}/log",
                             params={"since": since})

    def mint_terminal_token(self, bench: str) -> dict:
        return self._request("POST", "/v1/terminal-tokens",
                             json={"bench": bench})

    # ---- routes -------------------------------------------------------

    def put_routes(self, routes: list[dict]) -> dict:
        return self._request("PUT", "/v1/routes", json={"routes": routes})


def get_client() -> DockerManagerClient:
    """Module-level cache; one client per worker."""
    if not hasattr(frappe.local, "_barista_dm_client"):
        frappe.local._barista_dm_client = DockerManagerClient()
    return frappe.local._barista_dm_client
