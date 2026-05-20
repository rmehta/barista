"""Test fixtures for docker-manager.

We stub the Docker SDK so tests don't need a daemon. Each test gets
its own Flask `app` with a fresh stub.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add the docker-manager source to the path so tests can import `src`.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BARISTA_DOCKER_MANAGER_TOKEN", "testtoken")
os.environ.setdefault("BARISTA_DM_ALLOWED_CIDRS", "0.0.0.0/0")
os.environ.setdefault("BARISTA_DATA_ROOT", str(ROOT / "tests" / "fixture_data"))


@pytest.fixture
def docker_stub(monkeypatch):
    """Replace docker.from_env() with a configurable mock."""
    import docker
    client = MagicMock(name="DockerClient")
    client.version.return_value = {"Version": "test-25.0"}
    client.info.return_value = {"ServerVersion": "test-25.0"}
    monkeypatch.setattr(docker, "from_env", lambda: client)
    return client


@pytest.fixture
def app(docker_stub):
    # ensure the fixture data dir exists for path validation
    Path(os.environ["BARISTA_DATA_ROOT"]).mkdir(parents=True, exist_ok=True)

    from src.app import create_app
    a = create_app()
    a.config["TESTING"] = True
    return a


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth():
    return {"X-Auth-Token": "testtoken"}
