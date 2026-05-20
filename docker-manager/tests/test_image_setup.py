"""Static checks on Dockerfile + entrypoint.sh that catch the
'manager user can't groupadd' bug class without needing to build the
image in CI."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _dockerfile_lines() -> list[str]:
    return (ROOT / "Dockerfile").read_text().splitlines()


def _entrypoint() -> str:
    return (ROOT / "entrypoint.sh").read_text()


def test_dockerfile_does_not_drop_to_manager_before_entrypoint():
    """Without root, entrypoint.sh can't `groupadd -g <host-docker-gid>`
    and the container crash-loops with 'groupadd: Permission denied'.

    Drop is done by `su` inside the entrypoint instead.
    """
    lines = _dockerfile_lines()
    entry_idx = next(i for i, ln in enumerate(lines)
                     if ln.strip().startswith("ENTRYPOINT"))
    pre_entry = lines[:entry_idx]
    user_lines = [ln for ln in pre_entry if ln.strip().startswith("USER ")]
    assert not any("manager" in ln for ln in user_lines), (
        "Dockerfile must NOT drop to USER manager before ENTRYPOINT; "
        "entrypoint.sh needs to run as root to add the manager user "
        "to the host docker group."
    )


def test_entrypoint_drops_privileges_via_su():
    """If we don't drop privileges, gunicorn (and any Python code
    inside it) runs as root inside the container — needlessly
    increasing blast radius if docker-manager is ever compromised."""
    text = _entrypoint()
    assert "exec su" in text
    # the manager username, not just the substring 'manager' from a comment
    assert "su -s /bin/bash manager" in text


def test_entrypoint_handles_host_docker_socket_gid():
    """The whole point of running as root in the entrypoint."""
    text = _entrypoint()
    assert "/var/run/docker.sock" in text
    assert "groupadd" in text
    assert "usermod" in text


def test_requirements_include_gunicorn():
    """entrypoint.sh execs gunicorn — it must be in requirements.txt
    or the container crash-loops with 'gunicorn: command not found'."""
    reqs = (ROOT / "requirements.txt").read_text().lower()
    assert "gunicorn" in reqs
