"""Container-creation policy. The single chokepoint that rejects
unsafe asks even if the caller (Barista) sends them by accident."""

from __future__ import annotations

import re
from pathlib import Path

from werkzeug.exceptions import BadRequest

_NAME_RX = re.compile(r"^[a-z][a-z0-9-]{1,30}$")

_IMAGE_ALLOWLIST_RX = re.compile(
    r"^(?:"
    r"ghcr\.io/frappe/[\w.-]+(?::[\w.-]+)?"
    r"|docker\.io/library/(?:mariadb|redis|traefik)(?::[\w.-]+)?"
    r"|(?:mariadb|redis|traefik)(?::[\w.-]+)?"
    r"|barista/[\w.-]+(?::[\w.-]+)?"
    r")$"
)

_BENCH_CAPS = {"CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE", "FOWNER", "KILL"}


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME_RX.match(name):
        raise BadRequest(f"invalid name: {name!r}")
    return name


def validate_image(image: str) -> str:
    if not isinstance(image, str) or not _IMAGE_ALLOWLIST_RX.match(image):
        raise BadRequest(f"image not in allowlist: {image!r}")
    return image


def validate_host_path(path: str, data_root: str) -> str:
    """Reject any bind-mount target outside the Barista data tree."""
    if not isinstance(path, str):
        raise BadRequest("host_path must be a string")
    resolved = Path(path).resolve()
    root = Path(data_root).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as e:
        raise BadRequest(f"host_path {path!r} is outside data_root {data_root!r}") from e
    if not resolved.is_dir():
        raise BadRequest(f"host_path {path!r} does not exist or is not a directory")
    return str(resolved)


def validate_port(port) -> int:
    try:
        p = int(port)
    except (TypeError, ValueError) as e:
        raise BadRequest(f"invalid port: {port!r}") from e
    if not (1024 <= p <= 65535):
        raise BadRequest(f"port out of range: {p}")
    return p


def validate_caps(caps) -> list[str]:
    caps = caps or []
    extra = set(caps) - _BENCH_CAPS
    if extra:
        raise BadRequest(f"capability not allowed: {sorted(extra)}")
    return list(caps)


def reject_dangerous(payload: dict) -> None:
    if payload.get("privileged"):
        raise BadRequest("privileged containers are not allowed")
    if payload.get("network_mode") in ("host", "none"):
        raise BadRequest("network_mode 'host'/'none' is not allowed")
    for m in payload.get("mounts", []) or []:
        if m.get("source") in ("/", "/etc", "/var", "/root", "/home"):
            raise BadRequest(f"refusing to bind-mount {m['source']!r}")
